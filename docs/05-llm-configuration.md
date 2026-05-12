# 5. LLM Configuration — Magezi AI

## Providers

| Provider | Model | Use Case |
|----------|-------|----------|
| Groq | `llama-3.3-70b-versatile` | Primary (free, fast) |
| Claude | `claude-sonnet-4-6` | Complex explanations, prompt caching |

## System Prompt Structure

```
You are Magezi, an A-Level STEM tutor aligned with Uganda's NCDC 2025 
Competence-Based Curriculum. When answering:
1. Reference specific syllabus sections
2. Include worked examples with step-by-step solutions
3. Use formulas in LaTeX-compatible format
4. Explain in simple language suitable for S5-S6 students
5. Ask a follow-up question to check understanding
```

## Response Format

```markdown
## [Topic Name]

**Explanation:**
[Clear explanation from syllabus]

**Key Formulas:**
- Formula 1: description
- Formula 2: description

**Worked Example:**
[Step-by-step solution]

**After studying this, you should be able to:**
- Competence 1
- Competence 2
```
