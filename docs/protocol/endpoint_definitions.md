# Endpoint Definitions

## P0: Adverse Safety Event Proxy

**Type**: Binary (0/1)
**Source**: Derived from CPET test flags (not prospective follow-up)
**Positive criteria**: any of the following during the index CPET session:
  - Significant arrhythmia requiring test termination
  - Exercise-induced hypoxemia (SpO2 < 88% or ≥4% drop from rest)
  - Hypertensive response (peak SBP > 220 mmHg)
  - ST depression ≥ 1.0 mm
  - Early termination for cardiac/pulmonary reason

**Leakage note**: The flag variables used to define P0 MUST be excluded from P0 features.

---

## P1: Exercise Safety Zone

**Type**: Ordinal 3-class (0=green, 1=yellow, 2=red)
**Primary criteria**: VO2peak %predicted + VE/VCO2 slope + EIH status
**Conflict resolution**: `take_worst` (if criteria suggest multiple zones, assign highest risk)

| Zone | Code | Primary Rule |
|---|---|---|
| Green | 0 | VO2peak ≥ 70% pred AND VE/VCO2 ≤ 30 AND no EIH |
| Yellow | 1 | VO2peak 50–70% pred OR VE/VCO2 30–36 |
| Red | 2 | VO2peak < 50% pred OR VE/VCO2 > 36 OR EIH |

See `configs/data/label_rules_v1.yaml` for complete rule specification.
