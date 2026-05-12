"""Conversation persistence for authenticated Magezi users.

Anonymous users continue locally in the frontend. Authenticated users get
conversation and message persistence in SQLite so chat history survives
browser restarts and backend session memory eviction.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_PATH = Path(
    os.getenv(
        "AUTH_DB_PATH",
        str(Path(__file__).resolve().parents[2] / "data" / "magezi_auth.db"),
    )
)
_db_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@dataclass
class ConversationSummary:
    id: str
    title: str
    subject: str | None
    locale: str
    session_id: str
    preview: str
    message_count: int
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "subject": self.subject,
            "locale": self.locale,
            "session_id": self.session_id,
            "preview": self.preview,
            "message_count": self.message_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ConversationMessage:
    id: str
    role: str
    content: str
    timestamp: float
    citations: list[dict[str, Any]]
    faithfulness_score: float | None
    retrieval_mode: str
    subject: str | None
    grounding_warning: bool
    escalation_required: bool
    escalation_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "citations": self.citations,
            "faithfulness_score": self.faithfulness_score,
            "retrieval_mode": self.retrieval_mode,
            "subject": self.subject,
            "grounding_warning": self.grounding_warning,
            "escalation_required": self.escalation_required,
            "escalation_reason": self.escalation_reason,
        }


def init_db() -> None:
    with _db_lock:
        conn = _get_db()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id          TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL,
                    title       TEXT NOT NULL DEFAULT '',
                    subject     TEXT DEFAULT NULL,
                    locale      TEXT NOT NULL DEFAULT 'en',
                    session_id  TEXT NOT NULL,
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                    ON conversations(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS messages (
                    id                  TEXT PRIMARY KEY,
                    conversation_id     TEXT NOT NULL,
                    role                TEXT NOT NULL,
                    content             TEXT NOT NULL,
                    timestamp           REAL NOT NULL,
                    citations_json      TEXT NOT NULL DEFAULT '[]',
                    faithfulness_score  REAL DEFAULT NULL,
                    retrieval_mode      TEXT NOT NULL DEFAULT '',
                    subject             TEXT DEFAULT NULL,
                    grounding_warning   INTEGER NOT NULL DEFAULT 0,
                    escalation_required INTEGER NOT NULL DEFAULT 0,
                    escalation_reason   TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_time
                    ON messages(conversation_id, timestamp ASC);
                """
            )
            conn.commit()
        finally:
            conn.close()


def _normalise_preview(content: str) -> str:
    preview = " ".join(content.split()).strip()
    if len(preview) <= 140:
        return preview
    return preview[:137].rstrip() + "..."


def _derive_title(content: str) -> str:
    title = " ".join(content.split()).strip()
    if not title:
        return "New chat"
    if len(title) <= 56:
        return title
    return title[:53].rstrip() + "..."


def _summary_from_row(row: sqlite3.Row) -> ConversationSummary:
    return ConversationSummary(
        id=row["id"],
        title=row["title"] or "New chat",
        subject=row["subject"],
        locale=row["locale"] or "en",
        session_id=row["session_id"],
        preview=row["preview"] or "",
        message_count=int(row["message_count"] or 0),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _message_from_row(row: sqlite3.Row) -> ConversationMessage:
    citations_raw = row["citations_json"] or "[]"
    try:
        citations = json.loads(citations_raw)
    except json.JSONDecodeError:
        citations = []
    return ConversationMessage(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        timestamp=float(row["timestamp"]),
        citations=citations,
        faithfulness_score=row["faithfulness_score"],
        retrieval_mode=row["retrieval_mode"] or "",
        subject=row["subject"],
        grounding_warning=bool(row["grounding_warning"]),
        escalation_required=bool(row["escalation_required"]),
        escalation_reason=row["escalation_reason"] or "",
    )


def ensure_conversation(
    user_id: str,
    conversation_id: str,
    *,
    session_id: str,
    locale: str = "en",
    subject: str | None = None,
    title: str = "",
) -> ConversationSummary:
    now = time.time()
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute(
                """
                SELECT c.*,
                       COALESCE((
                           SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id
                       ), 0) AS message_count,
                       COALESCE((
                           SELECT content FROM messages m
                           WHERE m.conversation_id = c.id
                           ORDER BY m.timestamp DESC
                           LIMIT 1
                       ), '') AS preview
                FROM conversations c
                WHERE c.id = ?
                """,
                (conversation_id,),
            ).fetchone()

            if row:
                if row["user_id"] != user_id:
                    raise PermissionError("Conversation does not belong to this user.")
                conn.execute(
                    """
                    UPDATE conversations
                    SET session_id = ?,
                        locale = ?,
                        subject = COALESCE(?, subject),
                        title = CASE
                            WHEN title = '' AND ? != '' THEN ?
                            ELSE title
                        END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (session_id, locale, subject, title, title, now, conversation_id),
                )
                conn.commit()
            else:
                conn.execute(
                    """
                    INSERT INTO conversations (
                        id, user_id, title, subject, locale, session_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        user_id,
                        title or "New chat",
                        subject,
                        locale,
                        session_id,
                        now,
                        now,
                    ),
                )
                conn.commit()

            return get_conversation(user_id, conversation_id)
        finally:
            conn.close()


def get_conversation(user_id: str, conversation_id: str) -> ConversationSummary:
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute(
                """
                SELECT c.*,
                       COALESCE((
                           SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id
                       ), 0) AS message_count,
                       COALESCE((
                           SELECT content FROM messages m
                           WHERE m.conversation_id = c.id
                           ORDER BY m.timestamp DESC
                           LIMIT 1
                       ), '') AS preview
                FROM conversations c
                WHERE c.id = ? AND c.user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
            if not row:
                raise KeyError("Conversation not found.")
            return _summary_from_row(row)
        finally:
            conn.close()


def list_conversations(user_id: str) -> list[ConversationSummary]:
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute(
                """
                SELECT c.*,
                       COALESCE((
                           SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id
                       ), 0) AS message_count,
                       COALESCE((
                           SELECT content FROM messages m
                           WHERE m.conversation_id = c.id
                           ORDER BY m.timestamp DESC
                           LIMIT 1
                       ), '') AS preview
                FROM conversations c
                WHERE c.user_id = ?
                ORDER BY c.updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [_summary_from_row(row) for row in rows]
        finally:
            conn.close()


def get_messages(user_id: str, conversation_id: str) -> list[ConversationMessage]:
    with _db_lock:
        conn = _get_db()
        try:
            owner = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if not owner:
                raise KeyError("Conversation not found.")
            rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
                """,
                (conversation_id,),
            ).fetchall()
            return [_message_from_row(row) for row in rows]
        finally:
            conn.close()


def get_recent_history(
    user_id: str, conversation_id: str, *, limit_pairs: int = 5
) -> list[dict[str, str]]:
    recent = get_messages(user_id, conversation_id)
    if not recent:
        return []

    pairs: list[dict[str, str]] = []
    pending_user = ""
    for msg in recent:
        if msg.role == "user":
            pending_user = msg.content
            continue
        if msg.role == "assistant" and pending_user:
            pairs.append({"user_message": pending_user, "bot_reply": msg.content})
            pending_user = ""

    return pairs[-limit_pairs:]


def append_turn_pair(
    user_id: str,
    conversation_id: str,
    *,
    session_id: str,
    locale: str,
    subject: str | None,
    user_message: str,
    assistant_message: str,
    assistant_meta: dict[str, Any] | None = None,
) -> ConversationSummary:
    assistant_meta = assistant_meta or {}
    now = time.time()
    derived_title = _derive_title(user_message)
    preview = _normalise_preview(assistant_message or user_message)

    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT title, user_id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                conn.execute(
                    """
                    INSERT INTO conversations (
                        id, user_id, title, subject, locale, session_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        user_id,
                        derived_title,
                        subject,
                        locale,
                        session_id,
                        now,
                        now,
                    ),
                )
            elif row["user_id"] != user_id:
                raise PermissionError("Conversation does not belong to this user.")

            conn.execute(
                """
                UPDATE conversations
                SET title = CASE
                        WHEN title = '' OR title = 'New chat' THEN ?
                        ELSE title
                    END,
                    subject = COALESCE(?, subject),
                    locale = ?,
                    session_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (derived_title, subject, locale, session_id, now, conversation_id),
            )

            conn.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, role, content, timestamp, citations_json,
                    faithfulness_score, retrieval_mode, subject, grounding_warning,
                    escalation_required, escalation_reason
                ) VALUES (?, ?, ?, ?, ?, '[]', NULL, '', ?, 0, 0, '')
                """,
                (
                    str(uuid.uuid4()),
                    conversation_id,
                    "user",
                    user_message,
                    now,
                    subject,
                ),
            )
            conn.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, role, content, timestamp, citations_json,
                    faithfulness_score, retrieval_mode, subject, grounding_warning,
                    escalation_required, escalation_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    conversation_id,
                    "assistant",
                    assistant_message,
                    now + 0.001,
                    json.dumps(assistant_meta.get("citations") or []),
                    assistant_meta.get("faithfulness_score"),
                    assistant_meta.get("retrieval_mode") or "",
                    assistant_meta.get("subject") or subject,
                    1 if assistant_meta.get("grounding_warning") else 0,
                    1 if assistant_meta.get("escalation_required") else 0,
                    assistant_meta.get("escalation_reason") or "",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    summary = get_conversation(user_id, conversation_id)
    return ConversationSummary(
        id=summary.id,
        title=summary.title,
        subject=summary.subject,
        locale=summary.locale,
        session_id=summary.session_id,
        preview=preview,
        message_count=summary.message_count,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    with _db_lock:
        conn = _get_db()
        try:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
