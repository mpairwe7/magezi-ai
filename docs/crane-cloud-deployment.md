# Crane Cloud Deployment — Magezi AI

A-Level STEM Tutor for Uganda, deployed on Crane Cloud RENU cluster.

## Production

| Field | Value |
|-------|-------|
| URL | https://magezi-ai-81c6f046.renu-01.cranecloud.io |
| Image | `landwind/magezi-ai:latest` |
| Size | ~5.5 GB |
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
docker build -t landwind/magezi-ai:latest -f Dockerfile.cranecloud .
docker push landwind/magezi-ai:latest
```

## Verified Endpoints

| Endpoint | Status | Response |
|----------|--------|----------|
| `/health` | 200 | `{"status":"ok","model":"magezi-stem-tutor","subjects":["physics","chemistry","biology","mathematics"]}` |
| `/v1/chat` | 200 | Groq LLM tutoring response |
| `/` | 200 | Frontend UI |
| `/docs` | 200 | Swagger API docs |
