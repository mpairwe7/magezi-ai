# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (FastAPI, Python 3.11+, run from `backend/`)
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # dev server
pytest tests/                                  # all tests
pytest tests/test_voice_vad.py -k prosody     # single test by name
python -m app.indexer                          # extract 4,457 passages from NCDC PDFs
```

### Frontend (Next.js 16, run from `frontend/`)
```bash
bun install
bun run dev          # next dev --turbopack -p 3334
bun run build        # produces standalone output (next.config.ts:7)
bun run lint         # next lint
bun run type-check   # tsc --noEmit
```

### Knowledge base
```bash
./scripts/reindex.sh           # rebuild Qdrant collection from knowledge-base/syllabus/*.json
./scripts/reindex.sh --check   # health check only
```

### Docker
```bash
docker compose up --build                          # full stack (redis + qdrant + api + frontend)
docker compose up redis qdrant api                 # backend only
docker build -f Dockerfile.cranecloud -t magezi .  # single-image production build for Crane Cloud
```

### Port conventions (intentionally mismatched across configs — read before changing)
| Config | Backend | Frontend |
|---|---|---|
| `frontend/package.json` dev script | — | 3334 |
| `.env` / `docker-compose.yml` | 8000 | 3000 |
| `.env.example` (`NEXT_PUBLIC_API_URL`) | 8802 | — |
| `Dockerfile.cranecloud` (supervisord) | 8081 internal, nginx fronts on 8080 | 3000 internal |

## Architecture

### LLM backend selection (`backend/app/llm.py`)
Detects backend at import time: `GROQ_API_KEY` → Groq Llama 3.3 70B; else `ANTHROPIC_API_KEY` → Claude Sonnet 4.6; else "none" (local formatted fallback). On HTTP 429, Groq path retries 3× with exponential backoff (2s, 4s), then falls through to `_chunk_fallback()` which streams the local response word-by-word over SSE — the frontend renders both paths identically. Claude path uses prompt caching (`cache_control={"type": "ephemeral"}`) on the ~4K-token NCDC system prompt and extended thinking for complex problems.

### Tutoring pipeline (`backend/app/service.py`)
The orchestrator (`TutoringService`) chains: `InputGuard` → `supervisor` (subject classify) → semantic cache → `query.rewrite` → `corrective_retrieve` (retriever + abstention) → `tutor_loop.plan_response` → LLM → `OutputGuard`. A `CircuitBreaker` (`resilience.py`) wraps LLM calls — 3 failures open the circuit for 15s up to 120s. Sessions are thread-safe `dict[sid] → {turns: deque(maxlen=20), last_access}` with 24h TTL and 5K cap; only the last 5 turns flow into the LLM prompt.

### Agentic tutor loop (`backend/app/agents/tutor_loop.py`)
Runs *before* generation, not as a separate LLM call. `plan_response()` performs keyword-based complexity detection (simple/moderate/complex → 2/4/6 steps), flags calculation-heavy queries to inject formulas via `tools.build_tool_context()`, and splits "compare X and Y" / "difference between" queries into multi-retrieval sub-queries. The plan is injected into the prompt as a teaching outline so the LLM follows NCDC pedagogy.

### Retrieval (`backend/app/retriever.py`)
Hybrid: BAAI/bge-m3 dense (1024-dim, multilingual — handles Luganda) + BM25 sparse via Qdrant's inverted index, fused with RRF, reranked by `mixedbread-ai/mxbai-rerank-base-v2`. BM25 vocab/IDF persists to `knowledge-base/bm25_state.json`. When Qdrant is unreachable, falls back to keyword search over `knowledge-base/syllabus/*.json` (4 JSON files, 68 structured competence entries) + `extracted/all_passages.json` (4,389 PDF-extracted chunks). `corrective_rag.py` adds abstention when grounding score < `GROUNDING_THRESHOLD` (default 0.3).

### STEM tools (`backend/app/tools.py`)
18 NIST CODATA constants + 47 formulas across 4 subjects + safe calculator (AST-based, no `eval`). `build_tool_context()` output is injected into every LLM prompt AND appended to the local fallback response, so students get formulas even when the LLM is down.

### Voice subsystem (`backend/app/voice_stream.py`, `voice_ws.py`)
WebSocket endpoint `/v1/voice/chat/stream`. Pipeline: PCM16 LE 20ms frames → energy gate (fast path, <0.1ms) → Silero VAD ONNX (~1ms, 1.6MB model, confirms speech, eliminates noise false-triggers) → utterance buffer → noise gate + semantic endpointing → ASR (Sunbird; falls back to on-device Whisper-tiny via `frontend/src/workers/whisperWorker.ts` using `@xenova/transformers`) → optional MT → LLM → optional MT back → prosody detection → sentence-chunked Sunbird TTS. `VOICE_SILERO_ENABLED=false` disables neural confirmation. Frame rate limited to 100/sec, 64KB max.

### Knowledge base (4,457 passages)
- 4 NCDC 2025 syllabus PDFs (288 pages) extracted to `knowledge-base/extracted/all_passages.json` via PyMuPDF in `indexer.py`, ~160-word chunks with overlap
- 4 structured JSON files in `knowledge-base/syllabus/` with topics, subtopics, competences (68 entries total)
- Multilingual bridge: 120 Luganda/Swahili/Runyankole → English term mappings

### SSE streaming + fallback parity
Both LLM tokens and local-fallback word chunks flow over `data:` SSE events. After the stream completes, `_save_turn()` writes to the session deque. Faithfulness scoring (token overlap) gates LLM responses; local fallback is trusted at 0.95. Citations attach to exact NCDC syllabus pages.

### Frontend chat (`frontend/src/`)
- `app/page.tsx`: mobile-first chat (100dvh, sticky composer, safe-area padding, scroll-to-bottom floating button when >200px from bottom)
- `components/ChatMessage.tsx`: react-markdown + remark-gfm + `normaliseMarkdown()`; Copy/Regenerate/Listen/👍👎 action buttons; expand/collapse with gradient fade for messages >1500 chars; citations rendered as `<details open>`
- State: Zustand stores `useChatStore` (chat, locale, subject, autoNarrate — persisted to localStorage) and `useAuthStore` (token + profile — separate persist key). TanStack Query handles health polling, feedback mutations, subjects list.
- On-device STT: `lib/onDeviceSTT.ts` + `workers/whisperWorker.ts` (Xenova/whisper-tiny, ~50MB, cached in IndexedDB), runs in Web Worker via ONNX Runtime WASM. CSP in `next.config.ts:32` allows `wasm-unsafe-eval` in production for this.

### Auth + persistence
SQLite at `data/magezi_auth.db`. Email signup → bcrypt → JWT (72h) → 50 free credits. BYOK accepts user's own Anthropic key in lieu of credit deduction. `conversations.py` persists threads; conversation TTL 7 days, session TTL 30 days (Uganda NDPA §19).

### Security
- CORS: `ALLOWED_ORIGINS` env, comma-separated. Default `*` in dev only.
- Rate limit: thread-safe sliding window (30 req/60s default), per-IP `deque`, stale-IP eviction at 10K keys
- `guardrails.InputGuard`: OWASP LLM01 prompt-injection patterns + exam-cheating detection
- Spotlighted passages: retrieved content wrapped in hash-bound markers (`llm.py`) so the LLM treats injected text as DATA, not instructions

### Deployment topologies
- **Dev**: `uvicorn` on 8000 + `bun run dev` on 3334, optional `docker compose up redis qdrant` for retrieval
- **Compose**: 4 services (redis, qdrant, api, frontend) — `frontend` builds with `NEXT_PUBLIC_API_URL` baked in
- **Crane Cloud**: single image (`Dockerfile.cranecloud`) running supervisord → nginx:8080 fronts uvicorn:8081 + node standalone:3000. `/v1/voice/` proxied with `Upgrade: websocket`. Backend runs as `magezi` user; logs flow to stdout/stderr via `/dev/stdout` symlinks.
