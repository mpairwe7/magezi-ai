# Crane Cloud Deployment — Magezi AI

A-Level STEM Tutor for Uganda, deployed on Crane Cloud RENU cluster.

## Production

| Field | Value |
|-------|-------|
| URL | https://magezi-ai-c53f499a.renu-01.cranecloud.io |
| App ID | `fef97411-c719-4465-b0f5-01d4fe56bd5e` |
| Project ID | `e30f272b-b7d8-4673-9605-2b76f8c6ef37` (MageziAI) |
| Image | `landwind/magezi-ai:latest` |
| Image digest | `sha256:cbded81fe177d2b8e91ba5a30e7a6e4376c618a2de5a26e23dbb7a1e22b897ab` |
| Size | 1.62 GB (was 5.5 GB before CPU torch wheel switch — 2026-05-13) |
| Port | 8080 (nginx → backend:8081 + frontend:3000) |
| Cluster | RENU (`9e81a70e-8460-4e5d-b0a8-17abcac30f68`) |
| GitHub | https://github.com/mpairwe7/magezi-ai |

## Environment Variables

| Key | Value | Description |
|-----|-------|-------------|
| `GROQ_API_KEY` | `gsk_...` (secret) | Groq free tier API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `LLM_BACKEND` | `groq` | LLM provider |
| `PORT` | `8081` | Backend port (internal) |
| `BM25_STATE_PATH` | Auto-resolved from `_PROJECT_ROOT` | Pre-built BM25 index |
| `LOG_LEVEL` | `info` | Logging level |

## Retrieval Fix for Crane Cloud

BM25 state now loads **before** Qdrant initialization, enabling keyword fallback without a vector store. Pre-built index: 4393 docs, 4989 terms from NCDC A-Level syllabus (Physics, Chemistry, Biology, Mathematics).

## Build & Deploy

```bash
# Build (CPU torch wheel pinned in Dockerfile.cranecloud — image ~1.6 GB)
docker build -t landwind/magezi-ai:latest -f Dockerfile.cranecloud .

# Push
docker push landwind/magezi-ai:latest

# Trigger redeploy on Crane Cloud (Kubernetes pulls :latest on pod restart).
# Token lives at ~/.cranecloud/token; app id is fef97411-… (see table above).
APP=fef97411-c719-4465-b0f5-01d4fe56bd5e
curl -X POST -H "Authorization: Bearer $(cat ~/.cranecloud/token)" \
  https://api.cranecloud.io/apps/$APP/restart

# Wait ~60 s for rolling deploy to settle, then verify
./scripts/verify_deploy.sh https://magezi-ai-c53f499a.renu-01.cranecloud.io
```

## Verified Endpoints

| Endpoint | Status | Response |
|----------|--------|----------|
| `/health` | 200 | `{"status":"ok","model":"magezi-stem-tutor","subjects":["physics","chemistry","biology","mathematics"]}` |
| `/v1/chat` | 200 | Groq LLM tutoring response |
| `/` | 200 | Frontend UI |
| `/docs` | 200 | Swagger API docs |

## Voice Streaming (Added 2026-05-12)

WebSocket endpoint `/v1/voice/chat/stream` added for real-time voice conversations.

| Feature | Status |
|---------|--------|
| Energy-based VAD | Enabled |
| Sentence-chunked TTS | Enabled |
| Barge-in | Enabled |
| Sunbird STT/TTS | Requires `SUNBIRD_API_TOKEN` |
| Multilingual (lg/nyn/sw) | Via Sunbird MT |

See `docs/voice-system.md` for full protocol documentation.

### Updated Production URL

```
https://magezi-ai-8e888a48.renu-01.cranecloud.io
```
