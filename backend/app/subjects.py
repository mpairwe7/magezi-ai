"""Authoritative subject registry for Magezi UI and API metadata."""

from __future__ import annotations

SUBJECT_REGISTRY: list[dict[str, object]] = [
    {
        "id": "physics",
        "name": "Physics",
        "name_lg": "Fizikisi",
        "icon": "atom",
        "color": "#3b82f6",
        "starter_prompts": [
            "Explain Newton's Second Law with a worked example",
            "How do I solve projectile motion problems?",
            "Nnyonnyola Ohm's Law (Explain Ohm's Law in Luganda)",
            "What is the photoelectric effect?",
        ],
    },
    {
        "id": "chemistry",
        "name": "Chemistry",
        "name_lg": "Kemisutti",
        "icon": "flask",
        "color": "#10b981",
        "starter_prompts": [
            "Explain the SN2 reaction mechanism step by step",
            "How do I balance redox equations?",
            "What is Le Chatelier's Principle?",
            "Describe the properties of Group 7 elements",
        ],
    },
    {
        "id": "biology",
        "name": "Biology",
        "name_lg": "Bayoloji",
        "icon": "dna",
        "color": "#f59e0b",
        "starter_prompts": [
            "Explain the stages of mitosis with diagrams",
            "How does photosynthesis work?",
            "Nnyonnyola DNA replication (Explain DNA replication)",
            "What is natural selection?",
        ],
    },
    {
        "id": "mathematics",
        "name": "Mathematics",
        "name_lg": "Okubala",
        "icon": "calculator",
        "color": "#8b5cf6",
        "starter_prompts": [
            "How do I integrate by parts?",
            "Solve: x² - 5x + 6 = 0 using the quadratic formula",
            "Prove the chain rule for differentiation",
            "What is the binomial distribution?",
        ],
    },
]


def list_subjects(enabled_subjects: list[str]) -> list[dict[str, object]]:
    enabled = set(enabled_subjects)
    return [subject for subject in SUBJECT_REGISTRY if str(subject.get("id")) in enabled]
