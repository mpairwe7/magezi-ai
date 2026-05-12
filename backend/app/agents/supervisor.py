"""Magezi supervisor agent — routes student queries to subject specialists.

Uses keyword-based classification to determine which subject tutor
should handle a query. This is lightweight and runs without an LLM call,
keeping latency low for the routing step.
"""

from __future__ import annotations

import logging
import re

from .state import RouteDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Subject keyword banks
# ---------------------------------------------------------------------------
SUBJECT_KEYWORDS: dict[str, set[str]] = {
    "physics": {
        "newton", "force", "acceleration", "velocity", "momentum", "energy",
        "wave", "frequency", "wavelength", "diffraction", "interference",
        "circuit", "resistance", "voltage", "current", "ohm", "capacitor",
        "magnetic", "electromagnetic", "induction", "faraday", "lenz",
        "nuclear", "radioactive", "decay", "half-life", "photon", "quantum",
        "projectile", "gravity", "gravitational", "kepler", "orbital",
        "thermodynamic", "entropy", "heat", "temperature", "gas law",
        "pressure", "density", "buoyancy", "archimedes",
        "optics", "lens", "mirror", "refraction", "reflection",
        "mechanics", "kinematics", "dynamics", "statics",
        "f=ma", "v=ir", "e=mc", "p=mv",
    },
    "chemistry": {
        "atom", "molecule", "element", "compound", "reaction", "equation",
        "organic", "inorganic", "alkane", "alkene", "alkyne", "alcohol",
        "acid", "base", "ph", "buffer", "titration", "indicator",
        "oxidation", "reduction", "redox", "electrolysis", "electrochemical",
        "bond", "ionic", "covalent", "metallic", "hydrogen bond",
        "periodic", "group", "period", "transition metal", "halogen",
        "mole", "avogadro", "concentration", "molarity", "dilution",
        "kinetics", "rate", "catalyst", "activation energy", "arrhenius",
        "equilibrium", "le chatelier", "kc", "kp",
        "enthalpy", "entropy", "gibbs", "hess", "calorimetry",
        "isomer", "functional group", "ester", "amine", "amide",
        "nucleophilic", "electrophilic", "substitution", "elimination",
        "sn1", "sn2", "e1", "e2", "mechanism",
        "polymer", "polymerisation", "monomer",
    },
    "biology": {
        "cell", "organelle", "mitochondria", "ribosome", "nucleus",
        "dna", "rna", "gene", "chromosome", "allele", "genotype", "phenotype",
        "mitosis", "meiosis", "cell division", "cytokinesis",
        "photosynthesis", "chloroplast", "chlorophyll", "light reaction",
        "respiration", "atp", "glycolysis", "krebs", "electron transport",
        "enzyme", "substrate", "active site", "inhibitor", "michaelis",
        "ecology", "ecosystem", "food chain", "food web", "trophic",
        "biodiversity", "conservation", "habitat", "niche",
        "evolution", "natural selection", "mutation", "adaptation",
        "nervous system", "neuron", "synapse", "reflex", "brain",
        "hormone", "endocrine", "insulin", "adrenaline",
        "immune", "antibody", "antigen", "vaccination", "pathogen",
        "heart", "blood", "circulation", "artery", "vein",
        "plant", "transpiration", "xylem", "phloem", "stomata",
        "osmosis", "diffusion", "active transport", "membrane",
        "protein", "carbohydrate", "lipid", "nucleic acid",
    },
    "mathematics": {
        "equation", "solve", "calculate", "formula", "theorem",
        "algebra", "quadratic", "polynomial", "factorize", "expand",
        "differentiate", "derivative", "integrate", "integration",
        "calculus", "limit", "continuity", "gradient", "tangent",
        "trigonometry", "sine", "cosine", "tangent", "sin", "cos", "tan",
        "logarithm", "exponential", "ln", "log", "index",
        "matrix", "determinant", "vector", "scalar", "dot product",
        "probability", "statistics", "mean", "median", "mode",
        "distribution", "normal", "binomial", "poisson",
        "hypothesis", "significance", "p-value", "chi-squared",
        "sequence", "series", "arithmetic", "geometric", "sum",
        "coordinate", "circle", "parabola", "ellipse", "hyperbola",
        "permutation", "combination", "factorial",
        "proof", "induction", "contradiction",
        "simultaneous", "inequality", "modulus",
        "fraction", "ratio", "percentage", "proportion",
    },
}

# Non-STEM indicators for escalation
NON_STEM_INDICATORS = {
    "cryptocurrency", "bitcoin", "politics", "election", "gossip",
    "dating", "relationship", "social media", "tiktok", "instagram",
    "football", "music", "movie", "game", "play", "entertainment",
    "recipe", "cooking", "fashion", "weather",
}


def classify(query: str) -> RouteDecision:
    """Classify a student query into a subject or meta-route.

    Returns a RouteDecision with the detected subject (or clarify/escalate).
    """
    q_lower = query.lower()
    tokens = set(re.findall(r"\w+", q_lower))

    # Check for non-STEM content
    non_stem_hits = tokens & NON_STEM_INDICATORS
    if len(non_stem_hits) >= 2:
        return RouteDecision(
            route="escalate",
            subject=None,
            confidence=0.8,
            reason=f"Non-STEM topic detected: {', '.join(non_stem_hits)}",
        )

    # Score each subject by keyword overlap
    scores: dict[str, int] = {}
    for subject, keywords in SUBJECT_KEYWORDS.items():
        # Check both single tokens and multi-word phrases
        score = len(tokens & keywords)
        # Also check phrases in the full query
        for kw in keywords:
            if " " in kw and kw in q_lower:
                score += 2
        scores[subject] = score

    total = sum(scores.values())
    if total == 0:
        # Very short or ambiguous query
        if len(tokens) < 3:
            return RouteDecision(
                route="clarify",
                subject=None,
                confidence=0.5,
                reason="Query too short to classify",
                clarification=(
                    "Could you tell me which subject this is about? "
                    "I can help with Physics, Chemistry, Biology, or Mathematics."
                ),
            )
        # Default to general RAG without subject filter
        return RouteDecision(
            route="rag",
            subject=None,
            confidence=0.3,
            reason="No subject-specific keywords detected",
        )

    best_subject = max(scores, key=lambda k: scores[k])
    confidence = scores[best_subject] / max(total, 1)

    return RouteDecision(
        route=best_subject,
        subject=best_subject,
        confidence=round(confidence, 2),
        reason=f"Keyword match: {best_subject} ({scores[best_subject]} hits)",
    )
