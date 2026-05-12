"""Pydantic v2 request/response schemas for Magezi API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HistoryTurn(BaseModel):
    """Minimal role/content turn payload sent by the client."""
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """Student chat request."""
    message: str = Field(..., min_length=1, max_length=2000, description="Student's question")
    top_k: int = Field(4, ge=1, le=10, description="Number of passages to retrieve")
    locale: str = Field("en", pattern=r"^(en|lg|sw|nyn)$", description="Response language")
    subject: str | None = Field(None, description="Subject filter: physics, chemistry, biology, mathematics")
    session_id: str | None = Field(None, description="Session ID for multi-turn context")
    conversation_id: str | None = Field(None, description="Conversation ID for persisted chat threads")
    history: list[HistoryTurn] = Field(default_factory=list, description="Recent turns for explicit context continuity")


class Citation(BaseModel):
    """A citation referencing a syllabus section or past paper."""
    ref: str
    source: str
    page: str | None = None
    section: str | None = None
    subject: str | None = None
    topic: str | None = None
    year: str | None = None
    paper: str | None = None
    passage: str | None = None


class ChatResponse(BaseModel):
    """Tutoring response with citations and metadata."""
    reply: str
    sources: list[str] = []
    citations: list[Citation] = []
    faithfulness_score: float | None = None
    retrieval_mode: str = "keyword"
    subject: str | None = None
    locale: str = "en"
    grounding_warning: bool = False
    escalation_required: bool = False
    escalation_reason: str = ""
    latency_ms: int | None = None
    credits_remaining: int | None = None
    conversation_id: str | None = None


class ConversationSummaryResponse(BaseModel):
    """Metadata about a stored conversation thread."""
    id: str
    title: str
    subject: str | None = None
    locale: str = "en"
    session_id: str
    preview: str = ""
    message_count: int = 0
    created_at: float
    updated_at: float


class ConversationMessageResponse(BaseModel):
    """A persisted chat turn."""
    id: str
    role: str
    content: str
    timestamp: float
    citations: list[Citation] = []
    faithfulness_score: float | None = None
    retrieval_mode: str = ""
    subject: str | None = None
    grounding_warning: bool = False
    escalation_required: bool = False
    escalation_reason: str = ""


class ConversationDetailResponse(BaseModel):
    """Conversation summary plus full message list."""
    conversation: ConversationSummaryResponse
    messages: list[ConversationMessageResponse] = []


class HealthResponse(BaseModel):
    """Service health check response."""
    status: str
    model: str
    retriever: str
    llm: str
    subjects: list[str]
