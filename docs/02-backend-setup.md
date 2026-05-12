# 2. Backend Setup — Magezi AI

## Endpoints (20 total)

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/auth/signup` | Student registration |
| POST | `/v1/auth/login` | JWT authentication |
| GET | `/v1/auth/me` | Current user + credits |
| POST | `/v1/auth/apikey` | BYOK (Bring Your Own Key) |

### Chat & Tutoring
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat` | Single-shot tutoring response |
| POST | `/v1/chat/stream` | SSE streaming tutoring |
| POST | `/v1/quiz` | Generate quiz + auto-grade |
| GET | `/v1/subjects` | Available subjects with prompts |

### Conversations
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/conversations` | List conversations |
| GET | `/v1/conversations/{id}` | Get conversation detail |
| DELETE | `/v1/conversations/{id}` | Delete conversation |
| POST | `/v1/session/clear` | Clear session |

### Voice & Language
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/tts` | Text-to-speech |
| POST | `/v1/asr` | Speech-to-text |
| POST | `/v1/translate` | Translation |
| GET | `/v1/speech/health` | Sunbird API health |
| WS | `/v1/voice/chat/stream` | Streaming voice tutoring |

## Service Layer — TutoringService

Competence-based RAG pipeline:
1. InputGuard (injection, profanity)
2. Subject classification (Physics/Chemistry/Biology/Maths)
3. Semantic cache lookup
4. Curriculum-aware retrieval (syllabus fallback)
5. Abstention check
6. LLM generation with NCDC competence framing
7. Citation formatting ([1] Syllabus reference)
8. OutputGuard (accuracy, grounding)
