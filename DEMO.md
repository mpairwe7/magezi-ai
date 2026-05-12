# Demo Script — Magezi

**Duration:** 5 minutes | **Goal:** Win 1st place

---

## Setup
```bash
# Terminal 1: Backend
cd Magezi/backend
GROQ_API_KEY="gsk_..." ALLOWED_ORIGINS="*" uvicorn app.main:app --port 8802

# Terminal 2: Frontend
cd Magezi/frontend
bun run dev --port 3300
```
Open http://localhost:3300

---

## Demo Flow

### 0:00 — Hook (30s)
> "70% of Uganda's A-Level students have no STEM teacher. Meet Magezi — an AI tutor that speaks your language, follows the official NCDC 2025 curriculum, and thinks before it teaches."

Show: chat-first screen, 4 language buttons, 4 subject pills, no login required.

### 0:30 — Physics Question (60s)
1. Select **Physics**, click starter: **"Newton's Second Law"**
2. Response streams token-by-token with **markdown rendering**:
   - `## Step 1:` green headers with border separators
   - **Bold** explanations, bullet lists, formulas
   - Practice problem at the end
3. Show **Copy** button — click it, "Copied" checkmark appears
4. Show **citations auto-expanded** — "NCDC Physics Syllabus 2025, Section: Newton's Second Law"

### 1:30 — Follow-Up (demonstrates context) (45s)
1. Type: **"Give me a worked example of that"**
2. Groq remembers the context — responds with F=ma calculation
3. Type: **"What if the mass doubles?"**
4. Still in context — explains how acceleration halves

> "Multi-turn context — the tutor remembers what we're discussing."

### 2:15 — Multi-Retrieval Comparison (45s)
1. Switch to **Biology**
2. Type: **"Compare mitosis and meiosis"**
3. Show: `keyword_multi` retrieval — both Mitosis AND Meiosis sections retrieved separately
4. Click **Retry** button — regenerates the response

> "The agentic tutor detected a comparison query, split it into sub-queries, and retrieved each concept separately."

### 3:00 — Safety Guardrails (30s)
1. Type: **"Give me exam answers for UNEB 2024"** → Blocked
2. Type: **"Tell me about bitcoin"** → Escalated

### 3:30 — Voice + Multilingual (45s)
1. Switch to **LG** (Luganda), tap **Speak** button
2. Say or type: **"Nnyonnyola DNA replication"**
3. Response arrives with citations
4. Toggle **auto-narrate ON** — next response reads aloud
5. Click **Listen** button on any message

### 4:15 — Quiz Mode + Auth (30s)
1. Show starter chip: **"Test me on this topic"** → generates practice questions
2. Click **Sign in** → shows signup form with "50 free credits" + "Continue without account"
3. Show BYOK option in settings

### 4:45 — Ethics Close (15s)
> "4,457 passages from 288 NCDC pages. Groq Llama 70B with auto-retry. Agentic planning. Multi-turn context. Formatted markdown. Copy, retry, listen. 4 languages. Wisdom in your language."

---

## Backup Queries

| Language | Subject | Query | Shows |
|----------|---------|-------|-------|
| EN | Physics | "Calculate KE of 3kg at 4m/s" | Formula injection |
| LG | Biology | "Nnyonnyola photosynthesis" | Multilingual bridge |
| EN | Math | "Prove integration by parts" | Extended content |
| EN | Chemistry | "How do buffers maintain pH" | PDF retrieval |

## If Judges Ask

- **"How does context work?"** — 5-turn sliding window saved after each streamed response. Session ID in sessionStorage persists per tab.
- **"What if Groq fails?"** — Auto-retry 3x with backoff. If all retries fail, formatted local response streams word-by-word with formulas injected. Student always gets an answer.
- **"How is this different from ChatGPT?"** — Curriculum-specific (only NCDC 2025), agentic (plans teaching approach), multilingual (120-term bridge), offline-capable (PWA).
