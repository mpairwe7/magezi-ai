"""Magezi STEM tools — calculator + formula lookup + constants.

These tools are injected as context into Claude's prompt so it can
reference exact constants, formulas, and verify calculations.
They also serve as fallback answers when Claude is unavailable.
"""

from __future__ import annotations

import math
import re

# ---------------------------------------------------------------------------
# Physical constants (NIST 2018 CODATA)
# ---------------------------------------------------------------------------
CONSTANTS: dict[str, dict[str, str]] = {
    "speed_of_light": {"symbol": "c", "value": "3.00 × 10⁸ m/s", "exact": "299792458"},
    "gravitational_constant": {"symbol": "G", "value": "6.674 × 10⁻¹¹ N m² kg⁻²", "exact": "6.67430e-11"},
    "planck_constant": {"symbol": "h", "value": "6.626 × 10⁻³⁴ J s", "exact": "6.62607e-34"},
    "boltzmann_constant": {"symbol": "k_B", "value": "1.381 × 10⁻²³ J K⁻¹", "exact": "1.38065e-23"},
    "avogadro_number": {"symbol": "N_A", "value": "6.022 × 10²³ mol⁻¹", "exact": "6.02214e23"},
    "elementary_charge": {"symbol": "e", "value": "1.602 × 10⁻¹⁹ C", "exact": "1.60218e-19"},
    "electron_mass": {"symbol": "m_e", "value": "9.109 × 10⁻³¹ kg", "exact": "9.10938e-31"},
    "proton_mass": {"symbol": "m_p", "value": "1.673 × 10⁻²⁷ kg", "exact": "1.67262e-27"},
    "gas_constant": {"symbol": "R", "value": "8.314 J mol⁻¹ K⁻¹", "exact": "8.31446"},
    "faraday_constant": {"symbol": "F", "value": "96 485 C mol⁻¹", "exact": "96485.3"},
    "permittivity_free_space": {"symbol": "ε₀", "value": "8.854 × 10⁻¹² F m⁻¹", "exact": "8.85419e-12"},
    "coulomb_constant": {"symbol": "k", "value": "8.988 × 10⁹ N m² C⁻²", "exact": "8.98755e9"},
    "stefan_boltzmann": {"symbol": "σ", "value": "5.670 × 10⁻⁸ W m⁻² K⁻⁴", "exact": "5.67037e-8"},
    "acceleration_gravity": {"symbol": "g", "value": "9.81 m/s²", "exact": "9.80665"},
    "atmospheric_pressure": {"symbol": "P₀", "value": "1.013 × 10⁵ Pa", "exact": "101325"},
    "speed_of_sound_air": {"symbol": "v_sound", "value": "340 m/s (at 20°C)", "exact": "343"},
    "specific_heat_water": {"symbol": "c_w", "value": "4 200 J kg⁻¹ K⁻¹", "exact": "4186"},
    "density_water": {"symbol": "ρ_w", "value": "1 000 kg m⁻³", "exact": "1000"},
}

# ---------------------------------------------------------------------------
# Key formulas by subject
# ---------------------------------------------------------------------------
FORMULAS: dict[str, list[dict[str, str]]] = {
    "physics": [
        {"name": "Newton's Second Law", "formula": "F = ma", "units": "N = kg × m/s²"},
        {"name": "Kinetic Energy", "formula": "KE = ½mv²", "units": "J"},
        {"name": "Gravitational PE", "formula": "PE = mgh", "units": "J"},
        {"name": "Work Done", "formula": "W = Fs cos(θ)", "units": "J"},
        {"name": "Power", "formula": "P = W/t = Fv", "units": "W"},
        {"name": "Momentum", "formula": "p = mv", "units": "kg m/s"},
        {"name": "Impulse", "formula": "J = FΔt = Δp", "units": "N s"},
        {"name": "Wave Speed", "formula": "v = fλ", "units": "m/s"},
        {"name": "Ohm's Law", "formula": "V = IR", "units": "V = A × Ω"},
        {"name": "Coulomb's Law", "formula": "F = kQ₁Q₂/r²", "units": "N"},
        {"name": "Centripetal Force", "formula": "F = mv²/r", "units": "N"},
        {"name": "SHM Period (spring)", "formula": "T = 2π√(m/k)", "units": "s"},
        {"name": "SHM Period (pendulum)", "formula": "T = 2π√(l/g)", "units": "s"},
        {"name": "Photoelectric", "formula": "hf = φ + ½mv²_max", "units": "J"},
        {"name": "de Broglie", "formula": "λ = h/(mv)", "units": "m"},
        {"name": "Radioactive Decay", "formula": "N = N₀e^(-λt), t½ = ln2/λ", "units": ""},
        {"name": "Ideal Gas Law", "formula": "pV = nRT", "units": "Pa × m³ = mol × J/K × K"},
        {"name": "Snell's Law", "formula": "n₁ sin(θ₁) = n₂ sin(θ₂)", "units": ""},
    ],
    "chemistry": [
        {"name": "Ideal Gas Law", "formula": "pV = nRT", "units": "Pa × m³ = mol × J/(mol·K) × K"},
        {"name": "Moles", "formula": "n = m/M = N/N_A", "units": "mol"},
        {"name": "Concentration", "formula": "c = n/V", "units": "mol/dm³"},
        {"name": "Rate Law", "formula": "Rate = k[A]^m[B]^n", "units": "mol dm⁻³ s⁻¹"},
        {"name": "Arrhenius", "formula": "k = Ae^(-Ea/RT)", "units": ""},
        {"name": "Hess's Law", "formula": "ΔH = ΣΔH_f(products) - ΣΔH_f(reactants)", "units": "kJ/mol"},
        {"name": "pH", "formula": "pH = -log₁₀[H⁺]", "units": ""},
        {"name": "Henderson-Hasselbalch", "formula": "pH = pKa + log([A⁻]/[HA])", "units": ""},
        {"name": "Nernst Equation", "formula": "E = E° - (RT/nF)ln(Q)", "units": "V"},
        {"name": "Faraday's Law", "formula": "m = MIt/(nF)", "units": "g"},
    ],
    "biology": [
        {"name": "Magnification", "formula": "M = image size / actual size", "units": "×"},
        {"name": "Water Potential", "formula": "ψ = ψ_s + ψ_p", "units": "kPa"},
        {"name": "Mitotic Index", "formula": "MI = dividing cells / total cells", "units": ""},
        {"name": "Respiratory Quotient", "formula": "RQ = CO₂ produced / O₂ consumed", "units": ""},
        {"name": "Simpson's Diversity", "formula": "D = 1 - Σ(n/N)²", "units": ""},
        {"name": "Chi-squared", "formula": "χ² = Σ(O-E)²/E", "units": ""},
        {"name": "Hardy-Weinberg", "formula": "p² + 2pq + q² = 1, p + q = 1", "units": ""},
    ],
    "mathematics": [
        {"name": "Quadratic Formula", "formula": "x = (-b ± √(b²-4ac)) / (2a)", "units": ""},
        {"name": "Discriminant", "formula": "Δ = b² - 4ac", "units": ""},
        {"name": "Binomial Expansion", "formula": "(a+b)ⁿ = Σ C(n,r) aⁿ⁻ʳ bʳ", "units": ""},
        {"name": "Differentiation (power)", "formula": "d/dx(xⁿ) = nxⁿ⁻¹", "units": ""},
        {"name": "Integration (power)", "formula": "∫xⁿ dx = xⁿ⁺¹/(n+1) + C", "units": ""},
        {"name": "Chain Rule", "formula": "dy/dx = dy/du × du/dx", "units": ""},
        {"name": "Product Rule", "formula": "d/dx(uv) = u'v + uv'", "units": ""},
        {"name": "Integration by Parts", "formula": "∫u dv = uv - ∫v du", "units": ""},
        {"name": "AP Sum", "formula": "S_n = n/2(2a + (n-1)d)", "units": ""},
        {"name": "GP Sum", "formula": "S_n = a(1-rⁿ)/(1-r)", "units": ""},
        {"name": "GP Sum to Infinity", "formula": "S_∞ = a/(1-r), |r| < 1", "units": ""},
        {"name": "Scalar Product", "formula": "a·b = |a||b|cosθ", "units": ""},
    ],
}


def lookup_constant(query: str) -> str | None:
    """Find a physical constant matching the query. Requires specific mention."""
    q = query.lower()
    for key, data in CONSTANTS.items():
        name = key.replace("_", " ")
        # Require at least 2 words from the constant name to match
        name_words = set(name.split())
        q_words = set(q.split())
        if len(name_words & q_words) >= 2:
            return f"{data['symbol']} = {data['value']}"
        # Or exact symbol match (single letter symbols excluded — too ambiguous)
        if len(data["symbol"]) > 1 and data["symbol"].lower() in q:
            return f"{data['symbol']} = {data['value']}"
    return None


def lookup_formula(query: str, subject: str | None = None) -> list[str]:
    """Find formulas matching the query. Requires 2+ word overlap for relevance."""
    q_words = set(query.lower().split())
    scored: list[tuple[int, str]] = []
    subjects = [subject] if subject and subject in FORMULAS else list(FORMULAS.keys())

    for subj in subjects:
        for f in FORMULAS.get(subj, []):
            name_words = set(f["name"].lower().split())
            overlap = len(q_words & name_words)
            if overlap >= 1:
                entry = f"{f['name']}: {f['formula']}"
                if f["units"]:
                    entry += f" ({f['units']})"
                scored.append((overlap, entry))

    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:3]]


def safe_calculate(expression: str) -> str | None:
    """Evaluate a simple mathematical expression safely.

    Only allows numbers, basic operators, and math functions.
    No exec/eval of arbitrary code.
    """
    # Strip whitespace and validate characters
    expr = expression.strip()
    if not re.match(r'^[\d\s\+\-\*/\(\)\.\^sincotaqrlgep]+$', expr):
        return None

    # Replace common notation
    expr = expr.replace('^', '**')
    expr = expr.replace('pi', str(math.pi))
    expr = expr.replace('e', str(math.e))

    # Whitelist only safe math operations
    safe_dict = {
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
        "exp": math.exp, "pi": math.pi, "abs": abs,
    }

    try:
        result = eval(expr, {"__builtins__": {}}, safe_dict)
        if isinstance(result, (int, float)):
            return f"{result:.6g}"
    except Exception:
        pass
    return None


def build_tool_context(query: str, subject: str | None = None) -> str:
    """Build tool context to inject into Claude's prompt.

    Returns relevant constants + formulas for the query,
    so Claude can reference exact values in its response.
    """
    parts: list[str] = []

    # Constants
    constant = lookup_constant(query)
    if constant:
        parts.append(f"Relevant constant: {constant}")

    # Formulas
    formulas = lookup_formula(query, subject)
    if formulas:
        parts.append("Relevant formulas:")
        for f in formulas:
            parts.append(f"  - {f}")

    return "\n".join(parts) if parts else ""
