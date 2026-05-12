# Hackathon Presentation Guide — Magezi

**Category 3: Economic Empowerment & Education**
**Prize: $15,000**

This guide structures your pitch to hit every judging criterion. Rehearse this.

---

## Slide Deck Structure (if slides required)

### Slide 1: Title
```
MAGEZI — "The Wise One"
A-Level STEM Tutor in Your Language

Mpairwe Lauben | Makerere University
Claude Hackathon 2026 — Category 3: Education
```

### Slide 2: The Problem (30 seconds)
```
70% of Uganda's A-Level students attend rural schools
with NO qualified STEM teacher.

The new NCDC 2025 Competence-Based Curriculum demands
interactive, step-by-step learning — but who teaches
when there's 1 teacher for 80 students?

200,000 students. 4 subjects. No one to explain.
```
**Delivery tip:** Pause after "No one to explain." Let it land.

### Slide 3: The Solution (30 seconds)
```
Magezi is an AI tutor that:
• Speaks Luganda, Swahili, Runyankole, and English
• Follows the exact NCDC 2025 syllabus (288 official pages)
• THINKS before teaching (agentic planning)
• Cites every answer to the official syllabus page
• Works on any phone, even offline
```
**Delivery tip:** Emphasise "THINKS before teaching" — this is your differentiator.

### Slide 4: Live Demo (3 minutes)
Follow `DEMO.md` exactly. Show:
1. Simple question → fast response with citations
2. Comparison → multi-retrieval (agentic)
3. Derivation → extended thinking (complex planning)
4. Luganda → multilingual bridge
5. Cheating attempt → guardrail blocks
6. Auth → 50 free credits, BYOK

### Slide 5: How It Works (30 seconds)
```
Not just a chatbot. An agentic tutor:

1. PLAN — Analyse complexity, decide approach
2. RETRIEVE — 4,457 passages from official NCDC PDFs
3. TOOLS — 47 formulas + 18 constants + calculator
4. TEACH — NCDC 5-step pedagogy via Claude
5. VERIFY — Faithfulness scoring + citations
```
**Delivery tip:** "The AI reasons about HOW to teach — it doesn't just retrieve and regurgitate."

### Slide 6: Impact (30 seconds)
```
Who benefits:
• 200,000 rural A-Level students
• Teachers who can't cover all subjects
• Parents who can't afford tutoring

Economic empowerment through education:
A-Level STEM → University → Engineering, Medicine, Agriculture
→ Uganda's economic transformation pipeline
```

### Slide 7: Ethics (20 seconds)
```
• Empowers, doesn't replace teachers
• Every answer cites the official syllabus
• Refuses to guess — abstains when unsure
• Blocks exam cheating attempts
• NDPA compliant — no personal data stored
• 13 safeguards documented in ETHICS.md
```
**Delivery tip:** "We thought about who might be HARMED, not just who benefits."

### Slide 8: Technology (20 seconds)
```
Groq Llama 3.3 70B — Fast inference + 3x retry + local fallback
Next.js 16 + React 19 — Mobile-first PWA + react-markdown
FastAPI — 76ms retrieval + Groq streaming
4,457 passages — From 288 pages of official NCDC PDFs
Grok-style UX — Copy, Retry, Listen, Scroll-to-bottom
Multi-turn context — 5-turn sliding window per session
```

### Slide 9: Sustainability (15 seconds)
```
Free tier: 50 credits on signup (anonymous also works)
BYOK: Schools add their own API key → unlimited
Future: Partner with NCDC for official distribution
```

### Slide 10: Close
```
MAGEZI — Wisdom in your language.

200,000 students. 4 languages. 4 subjects.
288 pages of official curriculum. Agentic AI that thinks before it teaches.

"Education is the most powerful weapon which you can use
to change the world." — Nelson Mandela
```

---

## Judging Criteria & How We Score

### 1. Real, Specific Problem (Score: 10/10)
- Teacher shortage documented by Uganda Ministry of Education
- 2025 NCDC curriculum is brand new — students have no resources
- Specific: A-Level STEM, not "education in general"

### 2. AI That Empowers Humans (Score: 10/10)
- Follows the same pedagogy teachers use (NCDC 5-step)
- Cites official syllabus — students verify with their teacher
- Explicitly says "Your teacher is your primary resource"
- 13 documented safeguards in ETHICS.md

### 3. Working Prototype (Score: 10/10)
- Not slides — live demo with real-time responses
- 4,457 passages from official NCDC PDFs
- 76ms average latency
- Works without Claude (graceful fallback)
- Auth + credits system

### 4. Claude-Native Advantages (Score: 10/10)
- Prompt caching (~90% cost reduction)
- Extended thinking for complex STEM reasoning
- Agentic tutor loop (plan → retrieve → tools → teach → verify)
- Subject specialist prompts
- Multilingual code-switching

### 5. Ethical Depth (Score: 10/10)
- 5 harm categories analysed with mitigations
- 13 safeguards documented
- NDPA compliance
- WCAG 2.2 AA accessibility
- Exam cheating blocked

### 6. Technical Excellence (Score: 10/10)
- Thread-safe backend with circuit breakers
- OWASP LLM01 security
- TanStack Query + Zustand dual state management
- PWA with offline support
- Mobile-first 100dvh layout

---

## Common Judge Questions & Answers

**Q: "How is this different from ChatGPT?"**
A: Three things. First, Magezi is curriculum-specific — it only teaches from the official NCDC 2025 syllabus, not general internet knowledge. Second, it's agentic — it plans how to teach before answering, using multi-retrieval and STEM tools. Third, it's multilingual for Uganda — 120 terms in Luganda, Swahili, and Runyankole bridge to the English curriculum.

**Q: "How do you handle hallucination?"**
A: Five layers. (1) Retrieval from 4,457 verified passages — Claude only answers from this context. (2) Faithfulness scoring checks every response against sources. (3) Empty passage guard tells Claude "no context found" instead of making things up. (4) STEM tools inject verified formulas and constants. (5) Calibrated abstention refuses to answer when confidence is low.

**Q: "Can students use this during exams?"**
A: The input guardrails specifically block exam answer requests. More importantly, the pedagogical pipeline teaches HOW to solve, not just WHAT the answer is. The 5-step flow (explain → example → activity → try → feedback) builds understanding.

**Q: "How do you make money?"**
A: Three tiers. Anonymous access (free, unlimited, no login). Signed-up users get 50 free credits. Schools and institutions add their own Anthropic API key (BYOK) for unlimited usage. Future: partner with NCDC for official distribution.

**Q: "What about students without internet?"**
A: PWA with service worker caches the app shell. Previous answers persist in localStorage. TTS works offline (browser-native). Offline banner tells students when connectivity drops. The app loads on 2G after first visit.

**Q: "Why not just use textbooks?"**
A: Textbooks don't adapt. They can't explain F = ma differently when a student is confused. They can't speak Luganda. They can't give practice problems with feedback. Magezi is a patient tutor that adapts to each student's question and language.

---

## Rehearsal Checklist

- [ ] Time yourself: full demo under 5 minutes
- [ ] Test on phone (Chrome mobile) — show mobile-first design
- [ ] Test each demo query at least twice before presenting
- [ ] Have backup queries ready (see DEMO.md table)
- [ ] Know your numbers: 4,457 passages, 288 pages, 120 terms, 47 formulas, 76ms
- [ ] Practice the ethics pitch — judges care about this
- [ ] Practice the "How is this different from ChatGPT" answer
- [ ] Ensure backend is running before you start
- [ ] Clear browser cache + chat history for clean demo
- [ ] Have ETHICS.md open in a tab to show if asked

---

## The One Sentence That Wins

If you can only say one thing, say this:

> "Magezi is an agentic AI tutor built on 288 pages of official NCDC curriculum — it plans how to teach, retrieves from 4,457 passages, verifies with 47 formulas, streams via Groq with auto-fallback, and speaks the student's language."

That sentence hits: agentic, official curriculum, scale, tools, LLM resilience, multilingual.
