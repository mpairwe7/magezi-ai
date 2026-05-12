"""Magezi auth — email sign-up/sign-in with JWT + free credits.

Flow:
    1. POST /v1/auth/signup  — create account, get 50 free credits
    2. POST /v1/auth/login   — get JWT access token
    3. GET  /v1/auth/me      — get profile + remaining credits
    4. POST /v1/auth/apikey  — save user's own Anthropic key (BYOK)

Credits:
    - New users get FREE_CREDITS_ON_SIGNUP (default 50)
    - Each chat message costs 1 credit
    - Users with their own API key bypass credits entirely
    - Credits can be topped up (future: Stripe integration)

Storage: SQLite (zero-config, file-based, hackathon-friendly).
Production: swap to PostgreSQL via env variable.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import bcrypt
import jwt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "magezi-hackathon-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "72"))
FREE_CREDITS_ON_SIGNUP = int(os.getenv("FREE_CREDITS_ON_SIGNUP", "50"))
_DB_PATH = Path(os.getenv(
    "AUTH_DB_PATH",
    str(Path(__file__).resolve().parents[2] / "data" / "magezi_auth.db"),
))

_db_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
def _get_db() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id          TEXT PRIMARY KEY,
                    email       TEXT UNIQUE NOT NULL,
                    password    TEXT NOT NULL,
                    name        TEXT DEFAULT '',
                    credits     INTEGER DEFAULT 0,
                    api_key     TEXT DEFAULT '',
                    plan        TEXT DEFAULT 'free',
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

                CREATE TABLE IF NOT EXISTS usage_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    credits_used INTEGER DEFAULT 0,
                    timestamp   REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
            """)
            conn.commit()
            logger.info("Auth database initialised at %s", _DB_PATH)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------
@dataclass
class User:
    id: str
    email: str
    name: str
    credits: int
    api_key: str
    plan: str
    created_at: float

    @property
    def has_own_key(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("sk-"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "credits": self.credits,
            "has_api_key": self.has_own_key,
            "plan": self.plan,
        }


# ---------------------------------------------------------------------------
# Auth operations
# ---------------------------------------------------------------------------
def signup(email: str, password: str, name: str = "") -> tuple[User | None, str]:
    """Create a new user. Returns (user, error_message)."""
    email = email.strip().lower()
    if not email or "@" not in email:
        return None, "Invalid email address."
    if len(password) < 6:
        return None, "Password must be at least 6 characters."

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())
    now = time.time()

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO users (id, email, password, name, credits, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, email, hashed, name.strip(), FREE_CREDITS_ON_SIGNUP, now, now),
            )
            conn.commit()
            user = User(
                id=user_id, email=email, name=name.strip(),
                credits=FREE_CREDITS_ON_SIGNUP, api_key="", plan="free",
                created_at=now,
            )
            logger.info("User signed up: %s (%d free credits)", email, FREE_CREDITS_ON_SIGNUP)
            return user, ""
        except sqlite3.IntegrityError:
            return None, "An account with this email already exists."
        finally:
            conn.close()


def login(email: str, password: str) -> tuple[User | None, str]:
    """Authenticate user. Returns (user, error_message)."""
    email = email.strip().lower()

    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not row:
                return None, "No account found with this email."

            if not bcrypt.checkpw(password.encode(), row["password"].encode()):
                return None, "Incorrect password."

            user = User(
                id=row["id"], email=row["email"], name=row["name"],
                credits=row["credits"], api_key=row["api_key"], plan=row["plan"],
                created_at=row["created_at"],
            )
            return user, ""
        finally:
            conn.close()


def get_user_by_id(user_id: str) -> User | None:
    """Fetch user by ID."""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            return User(
                id=row["id"], email=row["email"], name=row["name"],
                credits=row["credits"], api_key=row["api_key"], plan=row["plan"],
                created_at=row["created_at"],
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------
def use_credit(user_id: str) -> tuple[bool, int]:
    """Deduct 1 credit. Returns (success, remaining_credits)."""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT credits, api_key FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return False, 0

            # Users with their own API key bypass credits
            if row["api_key"] and row["api_key"].startswith("sk-"):
                return True, row["credits"]

            if row["credits"] <= 0:
                return False, 0

            new_credits = row["credits"] - 1
            now = time.time()
            conn.execute(
                "UPDATE users SET credits = ?, updated_at = ? WHERE id = ?",
                (new_credits, now, user_id),
            )
            conn.execute(
                "INSERT INTO usage_log (user_id, action, credits_used, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, "chat", 1, now),
            )
            conn.commit()
            return True, new_credits
        finally:
            conn.close()


def save_api_key(user_id: str, api_key: str) -> bool:
    """Save user's own Anthropic API key (BYOK)."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "UPDATE users SET api_key = ?, plan = ?, updated_at = ? WHERE id = ?",
                (api_key, "byok" if api_key else "free", time.time(), user_id),
            )
            conn.commit()
            logger.info("API key saved for user %s", user_id)
            return True
        finally:
            conn.close()


def get_user_api_key(user_id: str) -> str:
    """Get the user's API key if set, else empty string."""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT api_key FROM users WHERE id = ?", (user_id,)).fetchone()
            return row["api_key"] if row and row["api_key"] else ""
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_token(user: User) -> str:
    """Create a JWT access token."""
    payload = {
        "sub": user.id,
        "email": user.email,
        "exp": time.time() + (JWT_EXPIRY_HOURS * 3600),
        "iat": time.time(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> str | None:
    """Verify JWT and return user_id, or None if invalid."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
