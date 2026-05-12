# 1. System Architecture — Magezi AI

A-Level STEM Tutor for Uganda — competence-based tutoring aligned with NCDC 2025 curriculum.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, Zustand, TanStack Query |
| Backend | FastAPI, Python 3.11, uvicorn |
| LLM | Groq (llama-3.3-70b) / Claude (prompt caching) |
| Retrieval | BM25 (4393 passages from NCDC syllabus) + Qdrant hybrid |
| Voice | Sunbird AI (STT/TTS/MT), WebSocket streaming |
| Auth | JWT (signup/login, credits system) |
| Deployment | Docker → Docker Hub → Crane Cloud RENU |

## Data Flow

```
Student (voice/text) → nginx:8080
    ├── / → Next.js:3000 (tutor UI)
    ├── /v1/* → uvicorn:8081 (FastAPI)
    └── /v1/voice/chat/stream → WebSocket

Backend Pipeline:
    Query → InputGuard → Subject classifier
        → Cache → Curriculum retrieval (BM25 + syllabus)
        → Abstention → LLM (Groq/Claude)
        → OutputGuard → Response
```

## Knowledge Base

NCDC A-Level syllabus: 4393 passages, 4989 terms
- Physics (mechanics, waves, electricity, modern physics)
- Chemistry (bonding, kinetics, organic, inorganic)
- Biology (cell biology, genetics, ecology, physiology)
- Mathematics (algebra, calculus, geometry, statistics)
