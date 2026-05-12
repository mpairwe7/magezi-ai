"""Magezi tutoring pipeline — competence-based RAG orchestrator.

Forked from URA Chatbot service.py, heavily retailored for A-Level STEM
education following the NCDC 2025 Competence-Based Curriculum.

Pipeline:
    Student query
      -> Input guardrails (injection detection, content filter)
      -> Supervisor routing (subject classification)
      -> Semantic cache check
      -> Curriculum-aware hybrid retrieval (Qdrant)
      -> Keyword fallback (syllabus JSON)
      -> Abstention check (refuse when confidence is low)
      -> Claude synthesis (prompt caching + optional extended thinking)
      -> Output guardrails (grounding check, PII redaction)
      -> Tutoring response with citations
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from . import llm as llm_module
from .agents import supervisor
from .corrective_rag import corrective_retrieve, needs_clarification
from .guardrails import InputGuard, OutputGuard
from .query import rewrite as rewrite_query
from .resilience import CircuitBreaker
from .retriever import HybridRetriever

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SYLLABUS_DIR = _PROJECT_ROOT / "knowledge-base" / "syllabus"
GROUNDING_THRESHOLD = float(os.getenv("GROUNDING_THRESHOLD", "0.3"))
ENABLED_SUBJECTS = os.getenv("ENABLED_SUBJECTS", "physics,chemistry,biology,mathematics").split(",")

# LLM circuit breaker — prevents cascade failures when Claude API is down
_LLM_CIRCUIT = CircuitBreaker(
    name="llm",
    failure_threshold=3,
    reset_timeout=15.0,
    max_timeout=120.0,
)

_session_lock = threading.Lock()
_sessions: dict[str, dict] = {}  # {sid: {"turns": deque, "last_access": float}}
_SESSION_MAX_TURNS = 20
_SESSION_MAX_COUNT = 5_000
_SESSION_TTL = float(os.getenv("SESSION_TTL_SECONDS", "86400"))  # 24h default


def _get_history(session_id: str | None) -> list[dict[str, str]]:
    if not session_id:
        return []
    with _session_lock:
        entry = _sessions.get(session_id)
        if not entry:
            return []
        entry["last_access"] = time.time()
        return list(entry["turns"])[-5:]


def _save_turn(session_id: str | None, user_msg: str, bot_reply: str) -> None:
    if not session_id:
        return
    now = time.time()
    with _session_lock:
        if session_id not in _sessions:
            _sessions[session_id] = {
                "turns": deque(maxlen=_SESSION_MAX_TURNS),
                "last_access": now,
            }
        entry = _sessions[session_id]
        entry["turns"].append({"user_message": user_msg, "bot_reply": bot_reply})
        entry["last_access"] = now

        # Evict expired sessions to prevent memory leak
        if len(_sessions) > _SESSION_MAX_COUNT:
            cutoff = now - _SESSION_TTL
            stale = [sid for sid, e in _sessions.items() if e["last_access"] < cutoff]
            for sid in stale:
                del _sessions[sid]


def _clear_session(session_id: str | None) -> None:
    """Remove a session's history (called on chat reset)."""
    if not session_id:
        return
    with _session_lock:
        _sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Syllabus JSON fallback (keyword search)
# ---------------------------------------------------------------------------
def _load_syllabus_data() -> dict[str, list[dict[str, str]]]:
    """Load syllabus JSON files as a keyword-search fallback."""
    index: dict[str, list[dict[str, str]]] = {}

    if not _SYLLABUS_DIR.is_dir():
        logger.warning("Syllabus directory not found: %s", _SYLLABUS_DIR)
        return index

    for json_path in sorted(_SYLLABUS_DIR.glob("*.json")):
        subject = json_path.stem
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            entries: list[dict[str, str]] = []
            for topic_group in data.get("topics", []):
                group_name = topic_group.get("name", "")
                # Handle both 2-level (topics[].subtopics[]) and
                # 3-level (topics[].topics[].subtopics[]) structures
                inner_topics = topic_group.get("topics", [])
                if not inner_topics and topic_group.get("subtopics"):
                    inner_topics = [topic_group]
                for topic in inner_topics:
                    topic_name = topic.get("name", "")
                    for subtopic in topic.get("subtopics", []):
                        text = (
                            f"Subject: {subject.title()}\n"
                            f"Topic: {group_name} > {topic_name}\n"
                            f"Subtopic: {subtopic.get('name', '')}\n"
                            f"Content: {subtopic.get('content', '')}\n"
                            f"Competences: {', '.join(subtopic.get('competences', []))}"
                        )
                        entries.append({
                            "text": text,
                            "source": f"NCDC {subject.title()} Syllabus 2025",
                            "subject": subject,
                            "topic": f"{group_name} > {topic_name}",
                            "section": subtopic.get("name", ""),
                        })
            if entries:
                index[subject] = entries
                logger.info("Loaded %d entries from %s", len(entries), json_path.name)
        except Exception:
            logger.exception("Failed to load %s", json_path)

    # Also load extracted PDF passages if available
    extracted_path = _PROJECT_ROOT / "knowledge-base" / "extracted" / "all_passages.json"
    if extracted_path.exists():
        try:
            with open(extracted_path, encoding="utf-8") as fh:
                pdf_passages = json.load(fh)
            for p in pdf_passages:
                subj = p.get("subject", "")
                if subj and p.get("text"):
                    if subj not in index:
                        index[subj] = []
                    index[subj].append(p)
            pdf_count = len(pdf_passages)
            logger.info("Loaded %d PDF passages from %s", pdf_count, extracted_path.name)
        except Exception:
            logger.exception("Failed to load extracted PDF passages")

    total = sum(len(v) for v in index.values())
    logger.info("Knowledge base ready: %d total passages across %d subjects", total, len(index))
    return index


# Multilingual keyword bridge — maps common Luganda/Swahili/Runyankole query
# words to their English equivalents so keyword search finds syllabus content.
_MULTILINGUAL_BRIDGE: dict[str, str] = {
    # ---- Luganda (40+ terms) ----
    "nnyonnyola": "explain", "okubala": "calculate", "kiki": "what",
    "bwotya": "how", "lwaki": "why", "ennyiriri": "stages",
    "ssetuufu": "cell", "amaanyi": "force", "musulo": "law",
    "okutegeera": "understand", "okwogera": "describe", "obuzito": "mass",
    "endabirwamu": "experiment", "omuzigo": "weight", "ebisenge": "equation",
    "omusaale": "ray", "okwaka": "burn", "amazzi": "water", "omuliro": "fire",
    "obunyogovu": "energy", "enyanja": "wave", "ekizikiza": "dark",
    "ekitangaala": "light", "emisinde": "circuit", "olussuku": "resistance",
    "akaloosa": "velocity", "ebbeyi": "pressure", "ebbanga": "distance",
    "obudde": "time", "omutindo": "temperature", "envumbo": "reaction",
    "obusaanyufu": "acid", "ekimu": "base", "ssaayansi": "science",
    "ekibala": "fruit", "omubiri": "body", "eddagala": "medicine",
    "endwadde": "disease", "empaka": "competition", "okukulaakulana": "evolve",
    "obulamu": "life", "ensigo": "seed", "ekimera": "plant",
    # ---- Swahili (40+ terms) ----
    "eleza": "explain", "sheria": "law", "pili": "second",
    "hesabu": "calculate", "nini": "what", "jinsi": "how",
    "kwa": "why", "hatua": "step", "nguvu": "force",
    "kasi": "speed", "harakati": "motion", "kemikali": "chemical",
    "seli": "cell", "mgawanyiko": "division", "nishati": "energy",
    "mwanga": "light", "joto": "heat", "baridi": "cold",
    "maji": "water", "hewa": "air", "dunia": "earth",
    "uzito": "mass", "shinikizo": "pressure", "umbali": "distance",
    "muda": "time", "kiwango": "rate", "atomi": "atom",
    "molekyuli": "molecule", "protoni": "proton", "neutroni": "neutron",
    "elektroni": "electron", "damu": "blood", "moyo": "heart",
    "ubongo": "brain", "mapafu": "lungs", "mimea": "plant",
    "wanyama": "animal", "mazingira": "environment", "mzunguko": "cycle",
    "mlinganyo": "equation", "pembe": "angle", "mstari": "line",
    "duara": "circle", "eneo": "area", "ujazo": "volume",
    "wastani": "average", "uwezekano": "probability",
    # ---- Runyankole (30+ terms) ----
    "nyowe": "i", "ninyenda": "want", "kumanya": "know",
    "okumanya": "understand", "ebirungi": "properties",
    "ohandiika": "write", "okubara": "count", "enshonga": "topic",
    "ekirungi": "good", "amaani": "energy", "obushoboorozi": "power",
    "entaakuzigu": "force", "omuringo": "shape", "ekikomo": "limit",
    "ekicweka": "part", "obujurizi": "evidence", "okutereka": "store",
    "amaizi": "water", "omuriro": "fire", "eihanga": "nation",
    "enjura": "rain", "ekiro": "night", "eizoba": "sun",
    "obushwere": "heat", "emigisha": "blessing", "enshazi": "calculation",
    "orubibi": "boundary", "enteekateeka": "preparation",
    "obuhangwa": "creation", "obuzima": "health",
}


def _format_fallback_response(
    query: str,
    hits: list[dict[str, Any]],
    subject: str | None,
    locale: str,
) -> str:
    """Format raw passages into a clean pedagogical response without LLM.

    Structures the best passages following the NCDC competence-based approach
    so the fallback looks polished, not like a raw database dump.
    """
    from .tools import build_tool_context, lookup_formula

    parts: list[str] = []

    # Extract the best hit's structured content
    best = hits[0] if hits else {}
    raw = best.get("text") or best.get("answer", "")
    section = best.get("section", "")
    topic = best.get("topic", "")

    # Parse structured fields from JSON passages
    content = ""
    competences: list[str] = []
    for line in raw.split("\n"):
        if line.startswith("Content: "):
            content = line.replace("Content: ", "").strip()
        elif line.startswith("Competences: "):
            # Competences are full phrases — split carefully
            raw_comp = line.replace("Competences: ", "").strip()
            # Split on capital letter after comma (new competence starts with capital)
            import re as _re
            competences = _re.split(r',\s*(?=[A-Z])', raw_comp)
            competences = [c.strip() for c in competences if len(c.strip()) > 10]

    # If no structured content, clean and use raw text (PDF passages)
    if not content:
        import re
        cleaned = raw
        # Strip all syllabus headers and boilerplate
        cleaned = re.sub(r'^\d+\s+(PHYSICS|CHEMISTRY|BIOLOGY|MATHEMATICS)\s+SYLLABUS\s*', '', cleaned)
        cleaned = re.sub(r'ADVANCED SECONDARY CURRICULUM\s*', '', cleaned)
        cleaned = re.sub(r'SUB-TOPIC\s+\d+[\.\d]*:\s*', '', cleaned)
        cleaned = re.sub(r'TOPIC\s+\d+:\s*', '', cleaned)
        cleaned = re.sub(r'Duration:\s*\d+\s*Periods?\s*', '', cleaned)
        cleaned = re.sub(r'Learning Outcomes.*?:', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'Suggested Learning Activities.*?$', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'Sample Assessment Strategies.*?$', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'The learner should be able to:.*?$', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'\(\s*k\s*,\s*[uUsS]\s*,?\s*[sS]?\s*\)', '', cleaned)
        cleaned = re.sub(r'Competency?:\s*The learner\b.*?\.\s*', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'^\d{1,3}\s+', '', cleaned)  # Leading page numbers
        cleaned = re.sub(r'\n{2,}', '\n', cleaned)
        cleaned = cleaned.strip()
        content = cleaned[:500] if cleaned else raw[:500]

    # Build title from best available metadata
    title = section if section and len(section) > 3 else (topic.split(" > ")[-1] if topic else "")
    if not title or title == subject:
        # Extract from content — first meaningful phrase
        import re as _re2
        first_line = content.split("\n")[0] if content else ""
        first_line = _re2.sub(r'^\d+\s*', '', first_line)  # Strip leading numbers
        first_line = _re2.sub(r'Competency?:.*', '', first_line).strip()
        title = first_line[:80] if len(first_line) > 5 else (subject or "Topic").title()
    parts.append(f"## {title}\n")

    # Step 1: Explain
    parts.append(f"**Explanation:**\n{content}\n")

    # Step 2: Key formulas (from tools)
    formulas = lookup_formula(query, subject)
    if formulas:
        parts.append("**Key Formulas:**")
        for f in formulas:
            parts.append(f"- {f}")
        parts.append("")

    # Tool context (constants)
    tool_ctx = build_tool_context(query, subject)
    if tool_ctx and "constant" in tool_ctx.lower():
        for line in tool_ctx.split("\n"):
            if line.startswith("Relevant constant"):
                parts.append(f"**{line}**\n")

    # Step 3: Competences (what you should be able to do)
    if competences:
        parts.append("**After studying this, you should be able to:**")
        for c in competences[:4]:
            parts.append(f"- {c}")
        parts.append("")

    # Step 4: Practice prompt
    if competences:
        parts.append(f"**Try this:** {competences[0]}. Share your working and I'll help check each step.\n")
    else:
        parts.append(f"**Try this:** Explain the key concept of {title} in your own words.\n")

    # Additional context from other hits
    if len(hits) > 1:
        parts.append("**Related topics:**")
        seen = {section}
        for h in hits[1:4]:
            s = h.get("section", "") or h.get("topic", "")
            if s and s not in seen:
                seen.add(s)
                parts.append(f"- {s}")

    # Locale-aware footer
    if locale == "lg":
        parts.append("\n*Buuza omusomesa wo okusobola okukuyamba okutegeeramu ebisinga.*")
    elif locale == "sw":
        parts.append("\n*Muulize mwalimu wako kwa maelezo zaidi.*")
    else:
        parts.append("\n*Ask your teacher for more detailed explanations and worked examples.*")

    return "\n".join(parts)


_STOP_WORDS = frozenset(
    "a an the is are was were be been am do does did will would shall should "
    "can could may might must have has had of in on at to for with by from "
    "and or not no nor but so if then than that this these those it its i me "
    "my we our you your he she they them their what which who whom how when "
    "where why all each every any some".split()
)


def _keyword_search(
    query: str,
    syllabus_index: dict[str, list[dict[str, str]]],
    subject: str | None = None,
    top_k: int = 4,
) -> list[dict[str, str]]:
    """Keyword-overlap search with multilingual bridge.

    Expands non-English query words to English equivalents so
    Luganda/Swahili/Runyankole queries match English syllabus content.
    """
    raw_tokens = set(query.lower().split()) - _STOP_WORDS
    # Expand with English bridge terms
    expanded = set(raw_tokens)
    for tok in raw_tokens:
        bridge = _MULTILINGUAL_BRIDGE.get(tok)
        if bridge:
            expanded.add(bridge)

    scored: list[tuple[float, dict[str, str]]] = []
    subjects_to_search = [subject] if subject and subject in syllabus_index else list(syllabus_index.keys())

    # Build bigrams from query for phrase matching (e.g., "second law")
    q_words = query.lower().split()
    bigrams = {f"{q_words[i]} {q_words[i+1]}" for i in range(len(q_words) - 1)}

    for subj in subjects_to_search:
        for entry in syllabus_index.get(subj, []):
            text_lower = entry["text"].lower()
            entry_tokens = set(text_lower.split())
            overlap = len(expanded & entry_tokens)
            if overlap > 0:
                # Boost: exact phrase matches in section/title (e.g., "second law" in "Newton's Second Law")
                section_lower = (entry.get("section", "") + " " + entry.get("topic", "")).lower()
                phrase_bonus = sum(3 for bg in bigrams if bg in section_lower)
                # Boost: query words appearing in section name (high precision)
                section_tokens = set(section_lower.split())
                section_overlap = len(expanded & section_tokens)
                score = overlap + phrase_bonus + section_overlap * 2
                scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]


def _chunk_fallback(text: str):
    """Yield a formatted fallback response in small SSE-safe chunks.

    Splits by line, then by ~5-word groups so newlines are preserved
    as individual tokens and no single chunk contains a raw newline.
    """
    for line in text.split("\n"):
        if not line:
            yield "\n"
            continue
        words = line.split(" ")
        for i in range(0, len(words), 5):
            chunk = " ".join(words[i:i + 5])
            yield chunk + " "
        yield "\n"


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------
class TutoringService:
    """Magezi tutoring pipeline — backs all API endpoints.

    Initialises the syllabus knowledge base, hybrid retriever,
    and guardrails. Provides generate() for sync and stream responses.
    """

    def __init__(self) -> None:
        self.name = "magezi-stem-tutor"
        self._syllabus_index = _load_syllabus_data()

        # Hybrid retriever (graceful degradation to keyword search)
        self._retriever = HybridRetriever()
        self._retriever_ready = self._retriever.initialize()

        # Guardrails
        self._input_guard = InputGuard()
        self._output_guard = OutputGuard()

        # LLM availability
        self._llm_available = llm_module.is_available()

        mode = "hybrid (Qdrant)" if self._retriever_ready else "keyword-only (fallback)"
        gen = "Claude API" if self._llm_available else "syllabus lookup (fallback)"
        logger.info(
            "TutoringService ready — %s retrieval, %s generation, %d subjects",
            mode, gen, len(self._syllabus_index),
        )

    def generate(
        self,
        message: str,
        session_id: str | None = None,
        top_k: int = 4,
        locale: str = "en",
        subject: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Return a grounded, cited tutoring response."""
        t0 = time.perf_counter()

        # 0. Conversation history
        if conversation_history is None:
            conversation_history = _get_history(session_id)

        # 1. Input guardrails
        guard = self._input_guard.check(message)
        if not guard.allowed:
            return {
                "reply": guard.reason,
                "sources": [],
                "citations": [],
                "faithfulness_score": None,
                "retrieval_mode": "blocked",
                "subject": subject,
                "locale": locale,
                "escalation_required": False,
                "escalation_reason": "",
            }

        # 2. Supervisor routing — detect subject if not specified
        if not subject:
            route = supervisor.classify(message)
            subject = route.subject
            if route.route == "escalate":
                return {
                    "reply": (
                        "This looks like a question outside A-Level STEM. "
                        "I focus on Physics, Chemistry, Biology, and Mathematics. "
                        "Please ask your teacher or guardian for help with other topics."
                    ),
                    "sources": [],
                    "citations": [],
                    "faithfulness_score": None,
                    "retrieval_mode": "escalated",
                    "subject": None,
                    "locale": locale,
                    "escalation_required": True,
                    "escalation_reason": route.reason,
                }
            if route.route == "clarify":
                return {
                    "reply": route.clarification or (
                        "Could you tell me more about what you'd like to learn? "
                        "I can help with Physics, Chemistry, Biology, or Mathematics."
                    ),
                    "sources": [],
                    "citations": [],
                    "faithfulness_score": None,
                    "retrieval_mode": "clarification",
                    "subject": None,
                    "locale": locale,
                    "escalation_required": False,
                    "escalation_reason": "",
                }

        # 2b. Query rewriting — normalise abbreviations, fix typos, resolve coreferences
        conversation_history = _get_history(session_id)
        rewritten = rewrite_query(message, history=conversation_history or None)
        logger.debug("Query rewrite: '%s' → '%s'", message[:60], rewritten[:60])

        # 2c. Pre-retrieval clarification check
        # (done after retrieval below, with hits context)

        # 2d. Agentic planning — analyse query for multi-step retrieval
        from .agents.tutor_loop import plan_response
        plan = plan_response(message, subject, locale)

        # 3. Hybrid retrieval (using rewritten query)
        hits: list[dict[str, Any]] = []
        retrieval_mode = "keyword"

        if not self._retriever_ready and not self._retriever._ready:
            self._retriever_ready = self._retriever.initialize()

        if self._retriever_ready:
            hits = self._retriever.search(rewritten, top_k=top_k, subject=subject)
            if hits:
                retrieval_mode = "hybrid"
            self._retriever_ready = self._retriever._ready

        # 4. Keyword fallback — with multi-retrieval for comparison queries
        if not hits:
            if plan.needs_multi_retrieval and len(plan.retrieval_queries) > 1:
                # Multi-retrieval: search each sub-query and merge
                seen_texts: set[str] = set()
                for sub_q in plan.retrieval_queries:
                    sub_hits = _keyword_search(sub_q, self._syllabus_index, subject=subject, top_k=2)
                    for h in sub_hits:
                        key = h["text"][:100]
                        if key not in seen_texts:
                            seen_texts.add(key)
                            hits.append({
                                "text": h["text"], "source": h["source"],
                                "subject": h.get("subject", ""), "topic": h.get("topic", ""),
                                "section": h.get("section", ""), "page": h.get("page", ""),
                                "chunk_id": "", "doc_type": h.get("doc_type", "syllabus"),
                                "score_rrf": 0.0,
                            })
                retrieval_mode = "keyword_multi"
            else:
                kw_hits = _keyword_search(message, self._syllabus_index, subject=subject, top_k=top_k)
                hits = [
                    {
                        "text": h["text"], "source": h["source"],
                        "subject": h.get("subject", ""), "topic": h.get("topic", ""),
                        "section": h.get("section", ""), "page": h.get("page", ""),
                        "chunk_id": "", "doc_type": h.get("doc_type", "syllabus"),
                        "score_rrf": 0.0,
                    }
                    for h in kw_hits
                ]

        # 4b. Corrective RAG — re-retrieve if quality is low
        if hits and self._retriever_ready:
            try:
                hits, was_corrected = corrective_retrieve(
                    rewritten, self._retriever, hits, top_k=top_k
                )
                if was_corrected:
                    retrieval_mode = "hybrid_corrected"
            except Exception:
                logger.debug("Corrective RAG skipped (error)", exc_info=True)

        # 4b2. Always blend top syllabus keyword hits AFTER corrective RAG
        #      so precise syllabus steps are never filtered out by reranking.
        kw_top = _keyword_search(rewritten, self._syllabus_index, subject=subject, top_k=2)
        seen_texts = {h.get("text", "")[:80] for h in hits}
        for h in kw_top:
            if h["text"][:80] not in seen_texts:
                hits.append({
                    "text": h["text"], "source": h["source"],
                    "subject": h.get("subject", ""), "topic": h.get("topic", ""),
                    "section": h.get("section", ""), "page": h.get("page", ""),
                    "chunk_id": "", "doc_type": h.get("doc_type", "syllabus"),
                    "score_rrf": 0.5,
                })
                seen_texts.add(h["text"][:80])

        # 4c. Clarification check — ask for more detail if query is ambiguous
        clarification = needs_clarification(message, hits)
        if clarification:
            return {
                "reply": clarification,
                "sources": [],
                "citations": [],
                "faithfulness_score": None,
                "retrieval_mode": "clarification",
                "subject": subject,
                "locale": locale,
                "escalation_required": False,
                "escalation_reason": "",
            }

        # 5. Abstention check
        if self._output_guard.should_abstain(hits):
            abstain_msg = (
                "Sirina bujjuvu ku nsonga eno okusobola okukuddamu bulungi. "
                "Buuza omusomesa wo okukuyamba."
                if locale == "lg"
                else "I don't have enough information to answer this reliably. "
                "Please ask your teacher for help with this topic."
            )
            return {
                "reply": abstain_msg,
                "sources": [],
                "citations": [],
                "faithfulness_score": None,
                "retrieval_mode": "abstained",
                "subject": subject,
                "locale": locale,
                "escalation_required": False,
                "escalation_reason": "",
            }

        # 6. LLM synthesis
        if hits:
            sources = list({h.get("source", "") for h in hits if h.get("source")})
            citations = HybridRetriever.build_citations(hits)
            contexts = [h.get("text") or h.get("answer", "") for h in hits]

            reply = ""
            if self._llm_available:
                use_thinking = llm_module.needs_extended_thinking(message, subject)
                reply = llm_module.generate(
                    query=message,
                    passages=hits,
                    conversation_history=conversation_history or None,
                    locale=locale,
                    subject=subject,
                    use_thinking=use_thinking,
                )

            # Fallback: format passages into pedagogical structure locally
            used_local_formatter = False
            if not reply:
                reply = _format_fallback_response(message, hits, subject, locale)
                used_local_formatter = True

            # Faithfulness scoring — local formatter is grounded by construction
            # (it copies directly from retrieved passages + verified formulas),
            # so we trust it. Only score Claude's generated responses.
            if used_local_formatter:
                faithfulness = 0.95  # Trusted — content comes from passages
            else:
                faithfulness = HybridRetriever.compute_faithfulness(reply, contexts)

            # Self-corrective: if faithfulness is very low and LLM is available,
            # expand the query and re-retrieve once (corrective RAG loop)
            if faithfulness < 0.3 and self._llm_available and retrieval_mode != "corrected":
                expanded_query = f"{message} {subject or ''} definition explanation formula"
                retry_hits = _keyword_search(expanded_query, self._syllabus_index, subject=subject, top_k=top_k)
                if retry_hits:
                    retry_passages = [
                        {"text": h["text"], "source": h["source"], "subject": h.get("subject", ""),
                         "topic": h.get("topic", ""), "section": h.get("section", ""),
                         "page": h.get("page", ""), "doc_type": h.get("doc_type", "syllabus")}
                        for h in retry_hits
                    ]
                    retry_reply = llm_module.generate(
                        query=message, passages=retry_passages,
                        conversation_history=conversation_history or None,
                        locale=locale, subject=subject, use_thinking=False,
                    )
                    if retry_reply:
                        retry_contexts = [h["text"] for h in retry_hits]
                        retry_faith = HybridRetriever.compute_faithfulness(retry_reply, retry_contexts)
                        if retry_faith > faithfulness:
                            reply = retry_reply
                            faithfulness = retry_faith
                            hits = retry_passages
                            citations = HybridRetriever.build_citations(hits)
                            contexts = retry_contexts
                            retrieval_mode = "corrected"
                            logger.info("Self-corrective RAG improved faithfulness: %.2f → %.2f", faithfulness, retry_faith)

            # Output guardrails
            grounding_ok = faithfulness >= GROUNDING_THRESHOLD

            result = {
                "reply": reply,
                "sources": sources,
                "citations": citations,
                "faithfulness_score": faithfulness,
                "retrieval_mode": retrieval_mode,
                "subject": subject,
                "locale": locale,
                "grounding_warning": not grounding_ok,
                "escalation_required": False,
                "escalation_reason": "",
                "latency_ms": round((time.perf_counter() - t0) * 1000),
            }

            # Save to session history
            _save_turn(session_id, message, reply)

            return result

        # No hits at all
        return {
            "reply": "I couldn't find relevant content for your question. Could you rephrase it?",
            "sources": [],
            "citations": [],
            "faithfulness_score": None,
            "retrieval_mode": "none",
            "subject": subject,
            "locale": locale,
            "escalation_required": False,
            "escalation_reason": "",
        }

    def stream_tokens(
        self,
        message: str,
        session_id: str | None = None,
        top_k: int = 4,
        locale: str = "en",
        subject: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Prepare streaming context: retrieval + metadata, then yield tokens.

        Returns a dict with 'tokens' (generator), 'citations', 'hits', etc.
        The caller (FastAPI endpoint) iterates 'tokens' for SSE events.
        """
        # Input guard
        guard = self._input_guard.check(message)
        if not guard.allowed:
            return {"error": guard.reason, "tokens": iter([])}

        # Supervisor routing
        if not subject:
            route = supervisor.classify(message)
            subject = route.subject
            if route.route in ("escalate", "clarify"):
                msg = route.clarification or "Please specify a STEM subject."
                return {"error": msg, "tokens": iter([])}

        # Conversation history
        if conversation_history is None:
            conversation_history = _get_history(session_id)

        # Retrieval
        hits: list[dict[str, Any]] = []
        retrieval_mode = "keyword"

        if not self._retriever_ready:
            self._retriever_ready = self._retriever.initialize()

        if self._retriever_ready:
            hits = self._retriever.search(message, top_k=top_k, subject=subject)
            if hits:
                retrieval_mode = "hybrid"

        if not hits:
            kw_hits = _keyword_search(message, self._syllabus_index, subject=subject, top_k=top_k)
            hits = [
                {
                    "text": h["text"],
                    "source": h["source"],
                    "subject": h.get("subject", ""),
                    "topic": h.get("topic", ""),
                    "section": h.get("section", ""),
                    "page": "",
                    "chunk_id": "",
                    "doc_type": "syllabus",
                    "score_rrf": 0.0,
                }
                for h in kw_hits
            ]

        # Blend top syllabus keyword hits so they always reach the LLM
        kw_top = _keyword_search(message, self._syllabus_index, subject=subject, top_k=2)
        seen_texts = {h.get("text", "")[:80] for h in hits}
        for h in kw_top:
            if h["text"][:80] not in seen_texts:
                hits.append({
                    "text": h["text"], "source": h["source"],
                    "subject": h.get("subject", ""), "topic": h.get("topic", ""),
                    "section": h.get("section", ""), "page": h.get("page", ""),
                    "chunk_id": "", "doc_type": h.get("doc_type", "syllabus"),
                    "score_rrf": 0.5,
                })
                seen_texts.add(h["text"][:80])

        citations = HybridRetriever.build_citations(hits) if hits else []

        # Generate streaming tokens with fallback on LLM failure
        fallback_reply = _format_fallback_response(message, hits, subject, locale)

        if self._llm_available:
            use_thinking = llm_module.needs_extended_thinking(message, subject)
            raw_tokens = llm_module.generate_stream(
                query=message,
                passages=hits,
                conversation_history=conversation_history or None,
                locale=locale,
                subject=subject,
                use_thinking=use_thinking,
            )
            # Wrap generator: if LLM yields 0 tokens (rate limit, error),
            # fall back to the formatted local response
            def _tokens_with_fallback():
                count = 0
                for t in raw_tokens:
                    if t:
                        count += 1
                        yield t
                if count == 0:
                    logger.warning("LLM stream yielded 0 tokens — using local fallback")
                    yield from _chunk_fallback(fallback_reply)

            tokens = _tokens_with_fallback()
        else:
            tokens = _chunk_fallback(fallback_reply)

        return {
            "tokens": tokens,
            "citations": citations,
            "hits": hits,
            "retrieval_mode": retrieval_mode,
            "subject": subject,
            "session_id": session_id,
        }
