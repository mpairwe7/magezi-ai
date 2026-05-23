"""Magezi FastAPI application — A-Level STEM Tutor API.

Endpoints:
    GET  /health               — Service health check
    POST /v1/auth/signup       — Create account (50 free credits)
    POST /v1/auth/login        — Get JWT access token
    GET  /v1/auth/me           — Profile + remaining credits
    POST /v1/auth/apikey       — Save own Anthropic key (BYOK)
    POST /v1/chat              — Synchronous tutoring response
    POST /v1/chat/stream       — SSE streaming tutoring response
    GET  /v1/subjects          — List available subjects
    POST /v1/feedback          — Submit feedback on a response
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# CPU-only inference tuning — must run before torch/sentence-transformers import.
# Caps thread fan-out so concurrent requests don't oversubscribe cores (default
# torch behaviour is one thread per core, which causes contention under load).
_cpu_threads = os.getenv("MAGEZI_CPU_THREADS") or str(max(1, min(4, (os.cpu_count() or 4))))
os.environ.setdefault("OMP_NUM_THREADS", _cpu_threads)
os.environ.setdefault("MKL_NUM_THREADS", _cpu_threads)
os.environ.setdefault("OPENBLAS_NUM_THREADS", _cpu_threads)
os.environ.setdefault("NUMEXPR_NUM_THREADS", _cpu_threads)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import auth, conversations
from .models import (
    ChatRequest,
    ChatResponse,
    ConversationDetailResponse,
    ConversationMessageResponse,
    ConversationSummaryResponse,
    HealthResponse,
)
from .service import TutoringService
from .subjects import list_subjects as list_subject_registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3500,http://localhost:3334"
).split(",")
ENABLED_SUBJECTS = os.getenv(
    "ENABLED_SUBJECTS", "physics,chemistry,biology,mathematics"
).split(",")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

# ---------------------------------------------------------------------------
# Thread-safe in-memory stores with TTL + bounded size
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_rate_store: dict[str, deque[float]] = {}
_RATE_STORE_MAX_KEYS = 10_000

_feedback_lock = threading.Lock()
_feedback_store: deque[dict] = deque(maxlen=10_000)

service: TutoringService | None = None


def _rate_limit_check(client_ip: str) -> bool:
    """Thread-safe sliding-window rate limiter. Returns True if allowed."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW

    with _rate_lock:
        entries = _rate_store.get(client_ip)
        if entries is None:
            entries = deque(maxlen=RATE_LIMIT_REQUESTS + 10)
            _rate_store[client_ip] = entries

        # Evict expired entries
        while entries and entries[0] <= window_start:
            entries.popleft()

        # Check BEFORE appending (fixes off-by-one)
        if len(entries) >= RATE_LIMIT_REQUESTS:
            return False

        entries.append(now)

        # Evict stale IPs periodically to prevent memory leak
        if len(_rate_store) > _RATE_STORE_MAX_KEYS:
            stale = [
                ip for ip, dq in _rate_store.items()
                if not dq or dq[-1] <= window_start
            ]
            for ip in stale:
                del _rate_store[ip]

    return True


def _get_client_ip(request: Request) -> str:
    """Extract client IP. Uses rightmost X-Forwarded-For (harder to spoof)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Rightmost entry is the one added by the trusted reverse proxy
        parts = [p.strip() for p in forwarded.split(",")]
        return parts[-1] if parts else "unknown"
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global service
    auth.init_db()
    conversations.init_db()
    service = TutoringService()
    logger.info("Magezi API started")
    yield
    logger.info("Magezi API shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Magezi API",
    description="A-Level STEM Tutor — Wisdom in your language",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-ID"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from . import llm as llm_module

    return HealthResponse(
        status="ok" if service else "starting",
        model="magezi-stem-tutor",
        retriever="ready" if (service and service._retriever_ready) else "unavailable",
        llm="ready" if llm_module.is_available() else "unavailable",
        subjects=ENABLED_SUBJECTS,
    )


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------
def _get_current_user(authorization: str | None) -> auth.User | None:
    """Extract user from Bearer token. Returns None for anonymous."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    user_id = auth.verify_token(token)
    if not user_id:
        return None
    return auth.get_user_by_id(user_id)


def _history_from_request(turns: list) -> list[dict[str, str]]:
    """Convert role/content turns into user/assistant history pairs."""
    if not turns:
        return []

    pairs: list[dict[str, str]] = []
    pending_user = ""

    for turn in turns[-12:]:
        role = getattr(turn, "role", "")
        content = getattr(turn, "content", "").strip()
        if not content:
            continue
        if role == "user":
            pending_user = content
            continue
        if role == "assistant" and pending_user:
            pairs.append({"user_message": pending_user, "bot_reply": content})
            pending_user = ""

    return pairs[-5:]


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    name: str = ""


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class ApiKeyRequest(BaseModel):
    api_key: str = Field("", description="Anthropic API key (sk-ant-...) or empty to remove")


@app.post("/v1/auth/signup")
async def auth_signup(body: SignupRequest):
    user, error = auth.signup(body.email, body.password, body.name)
    if error:
        return JSONResponse(status_code=400, content={"detail": error})
    token = auth.create_token(user)
    return {"token": token, "user": user.to_dict()}


@app.post("/v1/auth/login")
async def auth_login(body: LoginRequest):
    user, error = auth.login(body.email, body.password)
    if error:
        return JSONResponse(status_code=401, content={"detail": error})
    token = auth.create_token(user)
    return {"token": token, "user": user.to_dict()}


@app.get("/v1/auth/me")
async def auth_me(authorization: str | None = Header(None)):
    user = _get_current_user(authorization)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return {"user": user.to_dict()}


@app.post("/v1/auth/apikey")
async def auth_save_apikey(body: ApiKeyRequest, authorization: str | None = Header(None)):
    user = _get_current_user(authorization)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    if body.api_key and not body.api_key.startswith("sk-"):
        return JSONResponse(status_code=400, content={"detail": "Invalid API key format. Must start with sk-"})
    auth.save_api_key(user.id, body.api_key)
    updated = auth.get_user_by_id(user.id)
    return {"user": updated.to_dict() if updated else user.to_dict()}


# ---------------------------------------------------------------------------
# Conversation endpoints
# ---------------------------------------------------------------------------
@app.get("/v1/conversations", response_model=list[ConversationSummaryResponse])
async def list_conversations_endpoint(authorization: str | None = Header(None)):
    user = _get_current_user(authorization)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return [
        ConversationSummaryResponse(**conversation.to_dict())
        for conversation in conversations.list_conversations(user.id)
    ]


@app.get("/v1/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation_endpoint(conversation_id: str, authorization: str | None = Header(None)):
    user = _get_current_user(authorization)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    try:
        conversation = conversations.get_conversation(user.id, conversation_id)
        messages = conversations.get_messages(user.id, conversation_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})

    return ConversationDetailResponse(
        conversation=ConversationSummaryResponse(**conversation.to_dict()),
        messages=[ConversationMessageResponse(**message.to_dict()) for message in messages],
    )


@app.delete("/v1/conversations/{conversation_id}")
async def delete_conversation_endpoint(conversation_id: str, authorization: str | None = Header(None)):
    user = _get_current_user(authorization)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    try:
        summary = conversations.get_conversation(user.id, conversation_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})

    deleted = conversations.delete_conversation(user.id, conversation_id)
    if deleted:
        from .service import _clear_session
        _clear_session(summary.session_id)
    return {"status": "ok" if deleted else "not_found"}


# ---------------------------------------------------------------------------
# Synchronous chat
# ---------------------------------------------------------------------------
@app.post("/v1/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request, authorization: str | None = Header(None)):
    if not service:
        return JSONResponse(status_code=503, content={"detail": "Service starting"})

    if not _rate_limit_check(_get_client_ip(request)):
        return JSONResponse(
            status_code=429, content={"detail": "Rate limit exceeded. Please wait."}
        )

    # Credit check (if authenticated)
    user = _get_current_user(authorization)
    remaining = None
    if user:
        ok, remaining = auth.use_credit(user.id)
        if not ok:
            return JSONResponse(status_code=402, content={
                "detail": "No credits remaining. Add your own API key or upgrade your plan.",
                "credits": 0,
            })

    session_id = (
        body.session_id
        or request.headers.get("X-Session-ID")
        or str(uuid.uuid4())
    )
    conversation_history = _history_from_request(body.history)

    if user and body.conversation_id:
        try:
            conversations.ensure_conversation(
                user.id,
                body.conversation_id,
                session_id=session_id,
                locale=body.locale,
                subject=body.subject,
                title=body.message,
            )
        except PermissionError:
            return JSONResponse(status_code=403, content={"detail": "Conversation access denied."})
        if not conversation_history:
            conversation_history = conversations.get_recent_history(user.id, body.conversation_id)

    result = service.generate(
        message=body.message,
        session_id=session_id,
        top_k=body.top_k,
        locale=body.locale,
        subject=body.subject,
        conversation_history=conversation_history or None,
    )

    # Attach remaining credits to response
    if remaining is not None:
        result["credits_remaining"] = remaining
    result["conversation_id"] = body.conversation_id

    if user and body.conversation_id and result.get("reply"):
        conversations.append_turn_pair(
            user.id,
            body.conversation_id,
            session_id=session_id,
            locale=body.locale,
            subject=result.get("subject") or body.subject,
            user_message=body.message,
            assistant_message=result["reply"],
            assistant_meta={
                "citations": result.get("citations") or [],
                "faithfulness_score": result.get("faithfulness_score"),
                "retrieval_mode": result.get("retrieval_mode") or "",
                "subject": result.get("subject") or body.subject,
                "grounding_warning": result.get("grounding_warning", False),
                "escalation_required": result.get("escalation_required", False),
                "escalation_reason": result.get("escalation_reason") or "",
            },
        )

    return ChatResponse(**result)


# ---------------------------------------------------------------------------
# SSE streaming chat
# ---------------------------------------------------------------------------
@app.post("/v1/chat/stream")
async def chat_stream(
    body: ChatRequest, request: Request, authorization: str | None = Header(None),
):
    if not service:
        return JSONResponse(status_code=503, content={"detail": "Service starting"})

    if not _rate_limit_check(_get_client_ip(request)):
        return JSONResponse(
            status_code=429, content={"detail": "Rate limit exceeded. Please wait."}
        )

    # Credit check
    user = _get_current_user(authorization)
    remaining = None
    if user:
        ok, remaining = auth.use_credit(user.id)
        if not ok:
            return JSONResponse(status_code=402, content={
                "detail": "No credits remaining. Add your own API key or upgrade.",
                "credits": 0,
            })

    session_id = (
        body.session_id
        or request.headers.get("X-Session-ID")
        or str(uuid.uuid4())
    )
    conversation_history = _history_from_request(body.history)

    if user and body.conversation_id:
        try:
            conversations.ensure_conversation(
                user.id,
                body.conversation_id,
                session_id=session_id,
                locale=body.locale,
                subject=body.subject,
                title=body.message,
            )
        except PermissionError:
            return JSONResponse(status_code=403, content={"detail": "Conversation access denied."})
        if not conversation_history:
            conversation_history = conversations.get_recent_history(user.id, body.conversation_id)

    ctx = service.stream_tokens(
        message=body.message,
        session_id=session_id,
        top_k=body.top_k,
        locale=body.locale,
        subject=body.subject,
        conversation_history=conversation_history or None,
    )

    if ctx.get("error"):
        async def error_stream():
            yield f"event: error\ndata: {ctx['error']}\n\n"
            yield "event: done\ndata: \n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def token_stream():
        metadata = {
            "citations": ctx.get("citations", []),
            "retrieval_mode": ctx.get("retrieval_mode", "keyword"),
            "subject": ctx.get("subject"),
            "conversation_id": body.conversation_id,
            "credits_remaining": remaining,
        }
        yield f"event: metadata\ndata: {json.dumps(metadata)}\n\n"

        full_text = ""
        try:
            for token in ctx.get("tokens", []):
                if not token:
                    continue
                full_text += token
                yield f"data: {token}\n\n"
        except Exception:
            logger.exception("Token streaming error")
            yield "event: error\ndata: A streaming error occurred.\n\n"

        # Grounding check
        if ctx.get("hits"):
            if full_text:
                from .retriever import HybridRetriever
                contexts = [h.get("text") or h.get("answer", "") for h in ctx["hits"]]
                faithfulness = HybridRetriever.compute_faithfulness(full_text, contexts)
            else:
                faithfulness = 0.95
            grounding = {
                "faithfulness_score": faithfulness,
                "grounding_warning": faithfulness < float(os.getenv("GROUNDING_THRESHOLD", "0.3")),
            }
            yield f"event: grounding\ndata: {json.dumps(grounding)}\n\n"

        # Save conversation turn for multi-turn context
        if full_text and ctx.get("session_id"):
            from .service import _save_turn
            _save_turn(ctx["session_id"], body.message, full_text[:2000])

        if user and body.conversation_id and full_text:
            conversations.append_turn_pair(
                user.id,
                body.conversation_id,
                session_id=session_id,
                locale=body.locale,
                subject=ctx.get("subject") or body.subject,
                user_message=body.message,
                assistant_message=full_text[:4000],
                assistant_meta={
                    "citations": ctx.get("citations") or [],
                    "faithfulness_score": faithfulness if ctx.get("hits") else None,
                    "retrieval_mode": ctx.get("retrieval_mode", "keyword"),
                    "subject": ctx.get("subject") or body.subject,
                    "grounding_warning": grounding["grounding_warning"] if ctx.get("hits") else False,
                    "escalation_required": False,
                    "escalation_reason": "",
                },
            )

        yield "event: done\ndata: \n\n"

    return StreamingResponse(token_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Quiz generation — "Test me on this topic"
# ---------------------------------------------------------------------------
class QuizRequest(BaseModel):
    topic: str = Field(..., min_length=2, description="Topic to generate quiz on")
    subject: str | None = None
    num_questions: int = Field(3, ge=1, le=5)
    locale: str = "en"


@app.post("/v1/quiz")
async def generate_quiz(body: QuizRequest):
    """Generate practice questions from syllabus content.

    Works without Claude — extracts competences from syllabus entries
    and formats them as practice questions.
    """
    if not service:
        return JSONResponse(status_code=503, content={"detail": "Service starting"})

    from .service import _keyword_search
    hits = _keyword_search(body.topic, service._syllabus_index, subject=body.subject, top_k=body.num_questions + 2)

    if not hits:
        return {"questions": [], "topic": body.topic, "message": "No content found for this topic."}

    questions: list[dict] = []
    for i, hit in enumerate(hits[:body.num_questions]):
        text = hit.get("text", "")
        section = hit.get("section", hit.get("topic", ""))
        source = hit.get("source", "")

        # Extract competences if available
        comp_line = ""
        for line in text.split("\n"):
            if line.startswith("Competences:"):
                comp_line = line.replace("Competences:", "").strip()
                break

        # Build question from competence or content
        if comp_line:
            competences = [c.strip() for c in comp_line.split(",") if c.strip()]
            q_text = competences[0] if competences else f"Explain {section}"
        else:
            q_text = f"Explain the key concepts of: {section}"

        questions.append({
            "id": i + 1,
            "question": q_text,
            "topic": section,
            "source": source,
            "hint": text[:200] if text else "",
        })

    return {
        "questions": questions,
        "topic": body.topic,
        "subject": body.subject,
        "count": len(questions),
    }


# ---------------------------------------------------------------------------
# Session clear (called on "New session" / chat reset)
# ---------------------------------------------------------------------------
@app.post("/v1/session/clear")
async def clear_session(request: Request):
    """Clear a session's conversation history."""
    body = await request.json()
    session_id = body.get("session_id", "")
    if session_id:
        from .service import _clear_session
        _clear_session(session_id)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Subjects list
# ---------------------------------------------------------------------------
@app.get("/v1/subjects")
async def list_subjects():
    return {"subjects": list_subject_registry(ENABLED_SUBJECTS)}


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------
class FeedbackRequest(BaseModel):
    message_id: str = Field(..., min_length=1)
    rating: str = Field(..., pattern=r"^(up|down)$")
    user_query: str = ""
    bot_reply: str = ""


@app.post("/v1/feedback")
async def submit_feedback(body: FeedbackRequest):
    entry = {
        "message_id": body.message_id,
        "rating": body.rating,
        "bot_reply_preview": body.bot_reply[:200] if body.bot_reply else "",
        "timestamp": time.time(),
    }
    with _feedback_lock:
        _feedback_store.append(entry)
    logger.info("Feedback: message_id=%s rating=%s", body.message_id, body.rating)
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════
# Speech endpoints — Sunbird AI cloud (Luganda STT/TTS/MT)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/v1/speech/health")
async def speech_health():
    from .sunbird import is_available
    return {"status": "ready" if is_available() else "unavailable", "backend": "sunbird_cloud"}


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    language: str = "en"


@app.post("/v1/tts")
async def text_to_speech(body: TtsRequest):
    from .sunbird import text_to_speech as sunbird_tts, is_available
    if not is_available():
        return JSONResponse({"error": "Speech not configured (set SUNBIRD_API_TOKEN)"}, status_code=503)
    result = sunbird_tts(body.text, locale=body.language)
    if result and result.get("audio_url"):
        # Download and return as base64
        import httpx, base64
        try:
            audio_resp = httpx.get(result["audio_url"], timeout=15)
            if audio_resp.status_code == 200:
                audio_b64 = base64.b64encode(audio_resp.content).decode()
                return {"audio_base64": audio_b64, "backend": "sunbird_cloud"}
        except Exception:
            pass
    return {"audio_base64": None, "error": "TTS failed"}


@app.post("/v1/asr")
async def speech_to_text(request: Request):
    from .sunbird import speech_to_text as sunbird_stt, is_available
    if not is_available():
        return JSONResponse({"error": "Speech not configured"}, status_code=503)
    language = request.query_params.get("language", "en")
    audio_bytes = await request.body()
    if not audio_bytes:
        return JSONResponse({"error": "Empty audio"}, status_code=400)
    # Convert raw PCM to WAV for Sunbird
    import io, wave, struct, numpy as np
    try:
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype("float32") / 32768.0
        pcm16 = (samples * 32768).clip(-32768, 32767).astype("int16")
        sample_rate = int(request.query_params.get("sample_rate", "16000"))
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate)
            w.writeframes(pcm16.tobytes())
        lang_code = {"en": "eng", "lg": "lug", "sw": "swa", "nyn": "nyn"}.get(language, "eng")
        result = sunbird_stt(wav_buf.getvalue(), language=lang_code, filename="audio.wav")
        if result and result.get("text"):
            return {"text": result["text"], "language": result.get("language", language), "backend": "sunbird_cloud"}
    except Exception as e:
        logger.warning("ASR failed: %s", e)
    return {"text": "", "error": "ASR failed"}


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    source_language: str = "en"
    target_language: str = "lg"


@app.post("/v1/translate")
async def translate_text(body: TranslateRequest):
    from .sunbird import translate, is_available
    if not is_available():
        return JSONResponse({"error": "Translation not configured"}, status_code=503)
    src = {"en": "eng", "lg": "lug", "sw": "swa", "nyn": "nyn"}.get(body.source_language, body.source_language)
    tgt = {"en": "eng", "lg": "lug", "sw": "swa", "nyn": "nyn"}.get(body.target_language, body.target_language)
    result = translate(body.text, src, tgt)
    if result:
        return {"text": result, "source_lang": body.source_language, "target_lang": body.target_language, "backend": "sunbird_cloud"}
    return {"text": "", "error": "Translation failed"}


# ── Voice Streaming WebSocket ──────────────────────────────────────────────

@app.websocket("/v1/voice/chat/stream")
async def voice_chat_stream(websocket):
    """Streaming voice chat: audio → ASR → LLM → TTS over WebSocket."""
    from app.voice_ws import voice_stream_ws

    # Adapter: wrap the app's generate function for the voice pipeline
    def _generate_for_voice(query: str) -> dict:
        try:
            if hasattr(service, "generate"):
                from app.models import ChatRequest
                req = ChatRequest(query=query)
                resp = service.generate(req)
                return {"answer": resp.answer, "confidence": getattr(resp, "confidence", 0), "sources": getattr(resp, "sources", [])}
            else:
                return {"answer": "Voice service available but chat not configured.", "confidence": 0}
        except Exception as e:
            return {"answer": f"I encountered an error: {e}", "confidence": 0}

    # Get sunbird module
    try:
        from app import sunbird as _sunbird
    except ImportError:
        _sunbird = None

    await voice_stream_ws(websocket, _sunbird, _generate_for_voice)


