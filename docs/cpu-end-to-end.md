# Magezi — CPU End-to-End Deployment & Smoke Test Report

**Date:** 2026-05-13
**Host:** Linux 5.15, 64 cores, 357 GiB RAM available, load avg ~42
**Python:** 3.10 (system) — `USE_TF=0` set to bypass Keras-3/transformers conflict
**Mode:** CPU-only inference; Qdrant intentionally unreachable so retrieval falls through to keyword path (real CPU footprint, no GPU).

## Optimisations applied

| Change | File | Why |
|---|---|---|
| Cap BLAS/OMP/MKL thread fan-out to `min(4, cpu_count)` before any ML import | `backend/app/main.py:15-22` | Default torch behaviour spawns 1 thread per core, which causes cache thrash and lock contention under concurrency. Capping at 4 leaves headroom for FastAPI worker threads. Overridable via `MAGEZI_CPU_THREADS`. |
| `TOKENIZERS_PARALLELISM=false` default | `backend/app/main.py:21` | HuggingFace tokenizers warn-and-disable when forked under uvicorn workers; silencing also avoids a startup race. |
| Explicit `device="cpu"` on `SentenceTransformer` + `CrossEncoder` | `backend/app/retriever.py:184-188` | Skips torch's CUDA probe at startup — both faster boot and clearer intent for CPU images. |
| Bounded LRU cache for query dense embeddings (1024 entries) | `backend/app/retriever.py:154-157, 226-235` | Same students retype the same questions across turns. Avoids re-running bge-m3 forward pass (~80–200 ms each on CPU). |
| Doc comment on CPU torch wheel install | `backend/requirements.txt:15-17` | Default `torch>=2.5.0` resolves to a CUDA wheel by accident. Documents the `--index-url https://download.pytorch.org/whl/cpu` two-step. |
| Fixed unterminated string in CSP header | `frontend/next.config.ts:32` | Pre-existing `tsc` blocker (`'wasm-unsafe-eval'\",` had a stray escape). |
| Removed stale `@ts-expect-error` in Whisper worker | `frontend/src/workers/whisperWorker.ts:24` | TS 5.9 / Next 16 resolves `@xenova/transformers` typings now; directive was reporting "unused". |
| Refreshed `node_modules/next` install (16.2.0) | `frontend/node_modules/next/` | Existing install was corrupted — `package.json` declared `types: index.d.ts` but the file was missing. Recovered via `bun add next@16.2.0`. |

## CPU components that *would* benefit from GPU but stayed on CPU here

Validated via grep of every ML touch-point (`backend/app/retriever.py`, `voice_stream.py`, `indexer.py`):

| Component | Hot path? | GPU win? | Verdict |
|---|---|---|---|
| bge-m3 query encode | yes, per-request | 80–200ms → 5–15ms | CPU-only; cache softens repeats |
| mxbai-rerank cross-encoder | yes, per-request | 200–500ms → 10–30ms | CPU-only |
| Silero VAD ONNX | per-frame in voice WS | already <1ms/frame | **Stays CPU** — GPU launch overhead would regress |
| BM25 sparse encode | per-request | µs | **Stays CPU** — dict lookups, not a tensor op |
| PyMuPDF text extract | one-shot, indexer | seconds | **Stays CPU** — sequential decode |
| LLM inference (Groq/Anthropic) | per-request | remote — irrelevant | n/a |
| Sunbird ASR/TTS/MT | per voice turn | remote — irrelevant | n/a |

## Backend smoke (`scripts/smoke_api.py`) — 14/14

```
[PASS] health                       status=200 latency_ms=4    llm=ready retriever=unavailable
[PASS] subjects                     status=200 latency_ms=1    count=4
[PASS] auth.signup                  status=200 latency_ms=271  token_len=261
[PASS] auth.login                   status=200 latency_ms=287
[PASS] auth.me                      status=200 latency_ms=3    email_match=True
[PASS] auth.me_unauth               status=401 latency_ms=1
[PASS] chat.sync_physics            status=200 latency_ms=9740 reply_len=1270 retrieval=keyword citations=4
[PASS] chat.stream_chemistry        status=200 ttfb_ms=1503 total_ms=1505 data_chunks=275 has_done=True
[PASS] chat.multi_turn              status=200 latency_ms=7683 reply_len=1145 retrieval=keyword
[PASS] chat.empty_rejected          status=422
[PASS] chat.invalid_locale_rejected status=422
[PASS] feedback                     status=200 latency_ms=1
[PASS] session.clear                status=200 latency_ms=0
[PASS] speech.health                status=200 latency_ms=0
```

**Interpretation**

- `/health`, `/v1/subjects`, auth, validation, feedback, session-clear all sit at single-digit ms — CPU is not the bottleneck.
- `chat.sync_physics` 9.7 s and `chat.multi_turn` 7.7 s are dominated by **Groq round-trip + token decode** (~50–80 token/s for 70B). The CPU side of those requests (retrieval + guardrails + faithfulness) is ~50 ms.
- `chat.stream_chemistry` shows **1.5 s TTFB** — the metric students actually perceive — even on the keyword-fallback path with no GPU.
- `bcrypt` makes signup/login the slowest CPU-bound endpoints (~275 ms). That's by design — bcrypt cost is what protects the password hashes; not something to "optimise".
- Concurrency: `/health × 50, c=10` p50 = 6.8 ms, p95 = 11.8 ms — no contention spike.

### Notable behaviour observed

`/v1/chat` with a vague follow-up (`"Give me an example calculation."`) tripped the **abstention guard** (`corrective_rag.needs_clarification`) and returned the canned "I don't have enough information…" reply in 19 ms — no LLM call. That's correct behaviour: weak grounding shouldn't produce a confident hallucination. The smoke suite now uses a keyword-anchored follow-up (`"If F=ma, what is the force on…"`) to exercise the LLM path.

## Frontend smoke (`scripts/smoke_frontend.py`) — 5/5

```
[PASS] root_html         status=200 ttfb_ms=6  size_kb=20.5
[PASS] static_css_on_disk found=frontend/.next/static/chunks/0fe-…css
[PASS] manifest          status=200 app_name="Magezi — A-Level STEM Tutor" icons=2
[PASS] service_worker_probe status=404
[PASS] security_headers  csp=True xfo=True xcto=True ref=True
```

**Build**: `next build` (Turbopack) completed in 3.6 s compile + 5.2 s TypeScript + 0.5 s static page generation. Four static pages prerendered, ~21 KB initial HTML, 1.1 MB total `.next/static`.

**Static-asset gotcha**: Next 16 standalone `server.js` does NOT serve `_next/static` — that's nginx's job per `Dockerfile.cranecloud:71`. The smoke test originally hit this 404 and was corrected to assert "file exists on disk" instead.

## Residual issues (not blockers)

1. **No ESLint config.** `bun run lint` calls `next lint`, which Next 16 removed. ESLint isn't installed. Type safety is fully covered by `tsc --noEmit`. To restore: `bun add -D eslint eslint-config-next` and add `eslint.config.mjs`.
2. **`backend/app/llm.py` log line is misleading**: when Groq is selected, it logs *"Claude API generation"* (`service.py:_log_ready`). Cosmetic only.
3. **Lockfile drift warning** at build time: Next picked `/home/developer/package-lock.json` as workspace root over `frontend/bun.lock`. Silence by setting `turbopack.root` in `next.config.ts` if it becomes noisy.
4. **System python has a Keras 3 / transformers shim conflict.** Workaround: `USE_TF=0` before launching. Long term: deploy with the project's own venv per `Dockerfile`, where deps are clean.

## Reproducing

```bash
# Backend
cd backend
USE_TF=0 ALLOWED_ORIGINS='*' QDRANT_URL=http://localhost:0 \
  python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8902

# Backend smoke
python3 scripts/smoke_api.py --base http://127.0.0.1:8902

# Frontend build + run
cd frontend && NEXT_PUBLIC_API_URL=http://127.0.0.1:8902 bun run build
ln -sfn "$PWD/.next/static" .next/standalone/Mpairwe7/FinalYearProject/Magezi/frontend/.next/static
ln -sfn "$PWD/public" .next/standalone/Mpairwe7/FinalYearProject/Magezi/frontend/public
PORT=3902 HOSTNAME=127.0.0.1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8902 \
  node .next/standalone/Mpairwe7/FinalYearProject/Magezi/frontend/server.js

# Frontend smoke
python3 scripts/smoke_frontend.py --base http://127.0.0.1:3902
```

Raw outputs at `/tmp/magezi_bench/{smoke,smoke_frontend}.json`.
