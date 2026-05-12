# Ethics & Responsible AI — Magezi

## Who Benefits

### Primary Beneficiaries
- **Rural A-Level students** (est. 200,000+ in Uganda) who lack access to qualified STEM teachers, especially girls in STEM who face compounded disadvantage.
- **Teachers in understaffed schools** who can use Magezi as a teaching aid to extend their reach across subjects.
- **Parents and guardians** who want their children to succeed but cannot afford private tutoring.

### Secondary Beneficiaries
- **NCDC curriculum designers** — student interaction data reveals which topics are hardest, informing curriculum revision.
- **Education researchers** studying competence-based learning in low-resource contexts.

## Who Might Be Harmed

### Risk: Over-reliance on AI
**Mitigation:**
- Every response cites official NCDC syllabus pages. Students verify against the source.
- Faithfulness scoring triggers "Verify with your teacher" when grounding is low.
- Calibrated abstention — refuses to answer rather than guess.
- Empty passage guard — Claude receives explicit "no context" instead of hallucinating.
- Agentic tutor planner decides complexity and approach BEFORE generating.
- Feedback buttons (thumbs up/down) on every response via TanStack mutation.

### Risk: Exam Cheating
**Mitigation:**
- Input guardrails detect and block "give me exam answers" and UNEB answer requests.
- Pedagogical pipeline (explain → example → activity → try → feedback) builds understanding.
- System prompt refuses "just give the answer" without pedagogical scaffolding.

### Risk: Cultural & Linguistic Harm
**Mitigation:**
- Code-switching preserves English scientific terms — never force-translates "photosynthesis" or "acceleration".
- 120-term multilingual bridge (Luganda, Swahili, Runyankole) enables cross-language retrieval without mistranslation.
- Feedback buttons allow students to report language errors.

### Risk: Data Privacy
**Mitigation:**
- **Uganda NDPA SS19 compliance**: Sessions auto-expire (24h TTL, configurable).
- No PII collected — no names, school IDs, or location data required.
- Thread-safe session store bounded to 5K sessions max.
- Auth passwords bcrypt-hashed. JWT tokens expire in 72h.
- Feedback store bounded to 10K entries (no unbounded growth).

### Risk: Digital Divide Amplification
**Mitigation:**
- PWA with service worker — UI works offline after initial load.
- Voice-first design — Web Speech API + TTS for low-end phones.
- Mobile-first layout — 100dvh chat, sticky composer, collapsible hero.
- Offline detection banner shows "You are offline" with graceful degradation.

## Safeguards

| Safeguard | Implementation |
|-----------|---------------|
| Input filtering | OWASP LLM01 prompt-injection regex + education content + exam cheating block |
| LLM resilience | Groq retry (3x backoff on 429) → local fallback — student always gets an answer |
| Agentic planning | Tutor analyses complexity, decides multi-retrieval and tool use BEFORE answering |
| Output grounding | Faithfulness score with threshold — low scores trigger "verify" banner |
| Calibrated abstention | Refuses when retrieval confidence is too low |
| Empty passage guard | Claude receives "no context" instead of hallucinating from nothing |
| STEM tool verification | 18 constants + 47 formulas injected for numeric accuracy |
| Content guardrails | Refuses harmful, illegal, age-inappropriate, or off-topic content |
| Escalation | Routes non-STEM queries to "ask your teacher" |
| Rate limiting | Thread-safe sliding window (30 req/60s), bounded memory |
| Session TTL | 24h auto-expiry, 5K session max |
| Auth security | bcrypt passwords, JWT (72h expiry), BYOK key storage |
| CORS hardening | Configurable origins, credentials disabled |
| Feedback loop | Thumbs up/down on every response |

## Alignment with Hackathon Values

### AI That Empowers Humans
Magezi is a **supplement, not a replacement** for teachers. It follows the exact NCDC pedagogy teachers are trained in. Every response encourages verification with the teacher.

### Solving a Real Problem
The teacher-to-student ratio in rural Ugandan A-Level schools averages 1:80+. The 2025 competence-based curriculum demands interactive, activity-based learning that a single teacher cannot deliver to 80 students. Magezi fills the gap between lessons.

### Economic Empowerment Through Education
A-Level STEM qualifications unlock university admission in engineering, medicine, agriculture, and technology — careers that drive Uganda's economic transformation.

## Regulatory Compliance

| Regulation | Status |
|-----------|--------|
| Uganda National Data Protection Act (NDPA) 2019 | Compliant — SS19 data minimisation, session TTL, bounded stores |
| NCDC Curriculum Guidelines 2025 | Aligned — uses official 288-page syllabi as knowledge base |
| UNEB Examination Ethics | Respects — teaches methodology, blocks answer-giving |
| WCAG 2.2 AA Accessibility | Compliant — skip-link, focus-visible, reduced-motion, contrast 4.7:1 |

---

*Contact: mpairwelauben75@gmail.com*
