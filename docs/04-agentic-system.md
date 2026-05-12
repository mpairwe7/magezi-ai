# 4. Agentic System — Magezi AI

## Agent Architecture

```
Student query → Supervisor → Subject agent
                                  ↓
              Physics ← Chemistry ← Biology ← Mathematics
                                  ↓
                          Tutor Loop (multi-turn)
```

## Supervisor (`agents/supervisor.py`)

Keyword-based subject classifier:
- **Physics**: force, energy, momentum, wave, circuit, electricity
- **Chemistry**: bond, reaction, acid, organic, element, mole
- **Biology**: cell, DNA, enzyme, ecology, photosynthesis
- **Mathematics**: equation, integral, derivative, matrix, probability

## Tutor Loop (`agents/tutor_loop.py`)

Multi-turn tutoring interaction:
1. Identify student knowledge level from conversation history
2. Retrieve relevant syllabus passages
3. Generate explanation with worked examples
4. Ask follow-up question to check understanding
5. Provide formulas and key definitions
