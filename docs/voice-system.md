# Voice & Speech System — Magezi AI

Streaming voice pipeline for multilingual STEM tutoring in Luganda, Swahili, and English.

## Architecture

```
Student speaks → PCM16 chunks → WebSocket → VAD → ASR → [MT] → LLM (Groq)
                                                                    ↓
                                              STEM answer + formulas + diagrams
                                                                    ↓
                                                     [MT] → Sentence-chunked TTS
                                                                    ↓
                                                       Student hears explanation
```

## Endpoints

| Endpoint | Type | Description |
|----------|------|-------------|
| `POST /v1/tts` | HTTP | Batch text-to-speech |
| `WS /v1/voice/chat/stream` | WebSocket | Full streaming voice tutoring |

## WebSocket Protocol

### Client → Server
```json
{"type": "session_start", "language": "en", "vad_sensitivity": "medium", "tts_enabled": true}
// [binary: PCM16 LE mono 16kHz audio chunks]
{"type": "barge_in"}
{"type": "session_end"}
```

### Server → Client
```json
{"type": "session_ready", "session_id": "..."}
{"type": "vad_state", "speaking": true/false}
{"type": "transcript_final", "text": "...", "language": "en", "latency_s": 0.3}
{"type": "reply_text", "text": "In physics, Newton's second law states...", "chunk_index": 0}
{"type": "audio_start", "sample_rate": 24000}
// [binary: TTS audio]
{"type": "audio_end"}
{"type": "latency_report", "asr_ms": 300, "llm_ms": 600, "tts_first_chunk_ms": 200, "total_ms": 1100}
```

## Features

- **Energy-based VAD** — no neural model, works on CPU
- **Sentence-chunked TTS** — first audio in <1s
- **Barge-in** — student can interrupt mid-explanation
- **4 STEM subjects** — Physics, Chemistry, Biology, Mathematics (NCDC A-Level)
- **Multilingual** — English, Luganda, Swahili via Sunbird AI
- **BM25 retrieval** — 4393 passages from NCDC syllabus (pre-indexed)

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/voice_stream.py` | 301 | VAD + streaming pipeline |
| `backend/app/voice_ws.py` | 136 | WebSocket handler |
| `frontend/src/services/voiceWebSocket.ts` | 186 | WebSocket client + AudioRecorder |
| `frontend/src/services/voiceService.ts` | ~200 | Browser SpeechSynthesis TTS |

## Deployment

Production URL: https://magezi-ai-8e888a48.renu-01.cranecloud.io
Docker Hub: `landwind/magezi-ai:latest`
GitHub: https://github.com/mpairwe7/magezi-ai
