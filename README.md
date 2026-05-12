# Magezi — "The Wise One"

**Wisdom in your language — A-Level STEM Tutor**

> Helping rural students master the 2025 Competence-Based Curriculum, one step at a time.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Groq LLM](https://img.shields.io/badge/LLM-Groq%20Llama%2070B-orange)](https://groq.com)
[![Next.js 16](https://img.shields.io/badge/Frontend-Next.js%2016-black)](https://nextjs.org)
[![Python 3.11+](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com)
[![Knowledge Base](https://img.shields.io/badge/KB-4%2C457%20passages-gold)]()

---

## The Problem

Over **70% of Uganda's A-Level students** attend rural schools where qualified STEM teachers are scarce. The 2025 NCDC Competence-Based Curriculum demands higher-order thinking — but most students have no one to guide them.

**Magezi** is an AI tutor that speaks the student's language (Luganda, Swahili, Runyankole, English), follows the official NCDC 2025 syllabus, and teaches step by step.

## How It Works

```
Student asks a question (voice or text, any language)
  → Input guardrails (injection + cheating detection)
  → Supervisor classifies subject (zero-latency keyword classifier)
  → Agentic tutor plans response (complexity, multi-retrieval, tools)
  → Curriculum RAG (4,457 passages from 288 official NCDC PDF pages)
  → STEM tools inject verified formulas + constants
  → Groq Llama 3.3 70B generates pedagogical response (with retry)
  → Fallback: structured local response if LLM unavailable
  → Markdown rendering (headers, bold, lists, code, tables)
  → Faithfulness scoring + citations to exact syllabus pages
  → Multi-turn context (5-turn sliding window per session)
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Groq LLM** | Llama 3.3 70B via Groq — fast inference with auto-retry on 429 |
| **4,457 Passages** | 288 pages of official NCDC 2025 PDFs + structured JSON syllabus |
| **4 Languages** | Luganda, Swahili, Runyankole, English — 120-term multilingual bridge |
| **4 Subjects** | Physics, Chemistry, Biology, Mathematics (A-Level) |
| **Agentic Tutor** | Plans before answering: complexity analysis, multi-retrieval, tool use |
| **STEM Tools** | 18 physical constants + 47 formulas + safe calculator |
| **Markdown Chat** | react-markdown + remark-gfm: headers, bold, lists, code, tables render properly |
| **Grok-Style Actions** | Copy, Regenerate, Listen, Thumbs up/down on every response |
| **Voice I/O** | Web Speech API input + TTS output + auto-narrate toggle |
| **Multi-Turn Context** | 5-turn sliding window — follow-ups remember previous discussion |
| **Quiz Mode** | "Test me on Newton's Laws" generates competence-based practice questions |
| **Auth + Credits** | Email signup → 50 free credits → BYOK for unlimited |
| **Scroll-to-Bottom** | Floating button when scrolled up (Grok-inspired) |
| **Mobile-First** | 100dvh chat layout, sticky composer, collapsible hero |
| **Offline-Capable** | PWA + service worker + offline detection banner |
| **Citations** | Every answer cites exact NCDC syllabus page and section |
| **Graceful Fallback** | If LLM fails (rate limit), formatted local response with formulas |
| **WCAG 2.2 AA** | Skip-link, focus-visible, reduced-motion, contrast 4.7:1 |

## Architecture

```
                    +-------------------+
                    |   Next.js 16 PWA  |
                    | React 19 + Zustand|
                    | + TanStack Query  |
                    | react-markdown    |
                    +--------+----------+
                             |
                    +--------+----------+
                    |   FastAPI Gateway  |
                    | guardrails + auth  |
                    | rate limit + CORS  |
                    +--------+----------+
                             |
              +--------------+--------------+
              |              |              |
     +--------+---+  +------+------+  +----+--------+
     | Supervisor  |  | Tutor Loop  |  | STEM Tools  |
     | (classify)  |  | (plan →     |  | 18 constants|
     |             |  |  retrieve → |  | 47 formulas |
     |             |  |  synthesise)|  | calculator  |
     +--------+---+  +------+------+  +-------------+
              |              |
     +--------+---+  +------+------+
     | Curriculum  |  |  Groq API   |
     | RAG (4,457  |  | Llama 3.3   |
     | passages)   |  | 70B + retry |
     +-------------+  +-------------+
```

## Knowledge Base

| Source | Pages | Passages |
|--------|-------|----------|
| Physics.pdf (NCDC 2025) | 84 | 1,321 |
| CHEMISTRY.pdf (NCDC 2025) | 70 | 984 |
| Biology.pdf (NCDC 2025) | 44 | 576 |
| PRINCIPAL MATHS.pdf (NCDC 2025) | 90 | 1,440 |
| Structured JSON syllabus | — | 68 |
| **Total** | **288** | **4,457** |

## Quick Start

### Prerequisites
- Python 3.11+, Bun (or Node 20+)
- Groq API key (free tier: https://console.groq.com)

### 1. Configure
```bash
cd Magezi
cp .env.example .env
# Set GROQ_API_KEY in .env
```

### 2. Ingest knowledge base
```bash
cd backend
pip install pymupdf
python -m app.indexer
# Extracts 4,389 passages from 4 NCDC PDFs
```

### 3. Run
```bash
# Backend (terminal 1)
cd backend
uvicorn app.main:app --port 8802

# Frontend (terminal 2)
cd frontend
bun install && bun run dev --port 3300
```

### 4. Open
- Frontend: http://localhost:3300
- Backend: http://localhost:8802/docs

## Project Structure

```
Magezi/
├── README.md / ETHICS.md / DEMO.md / PRESENTATION.md / CLAUDE.md
├── .env.example
├── docker-compose.yml
├── backend/
│   └── app/
│       ├── main.py            # FastAPI + auth + SSE streaming + quiz
│       ├── service.py         # TutoringService — agentic pipeline + fallback
│       ├── llm.py             # Groq (Llama 70B) + Claude + retry + fallback
│       ├── retriever.py       # Hybrid retrieval (Qdrant + keyword)
│       ├── indexer.py         # PDF ingestion (PyMuPDF → chunks)
│       ├── tools.py           # 18 constants + 47 formulas + calculator
│       ├── auth.py            # Email auth + JWT + credits + BYOK
│       ├── guardrails.py      # OWASP LLM01 + cheating detection
│       └── agents/
│           ├── supervisor.py  # Subject classification
│           └── tutor_loop.py  # Agentic planning + multi-retrieval
├── frontend/
│   └── src/
│       ├── app/page.tsx       # Mobile-first chat + scroll-to-bottom
│       ├── components/
│       │   ├── ChatMessage.tsx # Markdown + copy/retry/listen + expand/collapse
│       │   ├── ChatInput.tsx   # Auto-resize textarea + mic + send
│       │   ├── AuthModal.tsx   # Signup-first + "Continue without account"
│       │   └── ...
│       ├── store/             # useChatStore + useAuthStore (Zustand)
│       ├── hooks/             # useApi (TanStack) + useSpeech + useOnlineStatus
│       └── services/          # voiceService (TTS + AudioRecorder)
├── knowledge-base/
│   ├── syllabus/              # 4 structured JSON files
│   └── extracted/             # 4,389 PDF-extracted passages
└── docs/                      # 4 official NCDC 2025 syllabus PDFs
```

## Team

**Mpairwe Lauben** — Makerere University, Final Year Computer Science

## Hackathon Category

**Category 3: Economic Empowerment & Education**

---

Built with Groq + Claude | Makerere University Claude Hackathon 2026
