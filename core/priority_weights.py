# T117 — deterministic queue priority weights.
#
# score = w_risk * risk_level + w_age * age_hours + w_specialist * specialist_weight
#
# These weights are intentionally simple defaults stored in the repo so the
# queue order is transparent and auditable.  Override via environment variables
# AEGIS_PRIORITY_W_RISK, AEGIS_PRIORITY_W_AGE, AEGIS_PRIORITY_W_SPECIALIST.
#
# Risk levels are mapped to numeric values:
#   L0=0, L1=1, L2=2, L3=3  (higher = more urgent).
W_RISK: float = 2.0
W_AGE: float = 0.5
W_SPECIALIST: float = 1.0

# Per-specialist weights (higher = higher priority in the queue).
# Defaults are uniform; all six specialists get the same weight.
SPECIALIST_WEIGHTS: dict[str, float] = {
    "Alina": 1.0,
    "Kian": 1.0,
    "Bita": 1.0,
    "Aylin": 1.0,
    "Ahmad": 1.0,
    "Amin": 1.0,
}

# Risk-level numeric mapping.
RISK_NUMERIC: dict[str, float] = {
    "L0": 0.0,
    "L1": 1.0,
    "L2": 2.0,
    "L3": 3.0,
}
