# 8. Security & Guardrails — Magezi AI

## Education-Specific Protections

- **Off-topic blocking**: Rejects non-STEM queries
- **Plagiarism guard**: Encourages understanding, not copy-paste
- **Age-appropriate content**: No violent/explicit content
- **Exam integrity**: Won't solve specific exam papers if detected

## OWASP LLM Top 10

Same framework as Musawo — InputGuard, OutputGuard, abstention, rate limiting.

## Auth Security

- JWT with expiry
- Password hashing (bcrypt)
- Credits system (prevent abuse)
- BYOK option (user provides own Anthropic key)
