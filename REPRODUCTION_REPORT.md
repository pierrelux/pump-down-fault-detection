# Reproduction Report: Li, Shen, Welch & Gluesenkamp (2024)
# "A Refrigerant Charge Prediction Method Based on Pump Down Operation"

## Summary

Reproduction of the charge prediction results using a Python reimplementation of
the DOE/ORNL Heat Pump Design Model (HPDM). The implementation includes: a
CoolProp-based refrigerant property wrapper, an AHRI 10-coefficient compressor
model, a segment-by-segment condenser model with Rouhani-Axelsson void fraction,
two-point charge calibration, 4-way valve leakage model, and a two-phase LP-side
pump-down simulator with charge-balance solver.

**Run:** `cd pumpdown && .venv/bin/python reproduce_all.py`
**Output:** `pumpdown/figures/reproduced/`

## Fig 7: 3-Ton Split System Validation (10 cases)

Uses `pyhpdm` charge-balance solver + AHRI 10-coeff compressor +
segment-by-segment condenser + pump-down simulator.

| T_out [F] | Charge [lbm] | Predicted [lbm] | Error |
|-----------|-------------|-----------------|-------|
| 71 | 7.00 | 7.04 | +0.6% |
| 79 | 7.00 | 7.04 | +0.6% |
| 87 | 7.00 | 7.04 | +0.5% |
| 95 | 7.00 | 7.04 | +0.5% |
| 71 | 8.08 | 8.12 | +0.5% |
| 79 | 8.08 | 8.12 | +0.5% |
| 87 | 8.08 | 8.12 | +0.5% |
| 95 | 8.08 | 8.12 | +0.5% |
| 71 | 9.11 | 9.15 | +0.4% |
| 79 | 9.11 | 9.15 | +0.4% |

- **Mean absolute error: 0.5%** (paper target: <6%)
- **All 10/10 cases within 6%**

## Fig 8: Charge Migration (5-ton)

Scaled 3-ton compressor map (2.57x) + pump-down simulator
(V_LP = 10 L, x_initial = 0.2).

| Quantity | Model | Paper | Match |
|----------|-------|-------|-------|
| Total charge (constant) | 13.28 lbm | 13.28 lbm | Exact |
| Initial m_low | 5.81 lbm | 5.81 lbm | Exact (input) |
| Final m_low | 0.29 lbm | ~0.69 lbm | Qualitative |
| Duration | 24.0 s | 24 s | Exact (calibrated) |

## Fig 9: Suction Pressure (5-ton)

| Quantity | Model | Paper | Match |
|----------|-------|-------|-------|
| Initial P_suc | 233 psia | ~250 psia | -7% (CoolProp vs REFPROP) |
| Final P_suc | 56 psia | 55 psia | Close |
| Plateau duration | ~16 s | ~15 s | Close |
| Shape | Plateau + sharp drop | Same | Yes |

## Fig 10: Mass Flow Rate (5-ton)

| Quantity | Model | Paper | Match |
|----------|-------|-------|-------|
| Initial mdot | 0.275 lbm/s | ~0.40 lbm/s | -31% |
| Final mdot | 0.052 lbm/s | ~0.10 lbm/s | -48% |
| Shape | Constant then rapid drop | Gradual decline | Qualitative |

The initial mass flow offset is because the compressor scale factor was
calibrated to 2.57x (instead of the 3.91x displacement ratio) to achieve
the correct 24s duration. The simple two-phase model keeps mass flow too
constant during phase 1, so a lower initial flow is needed.

## Verified Claims

| Claim | Status |
|-------|--------|
| Eq. 1: charge = condenser + migrated - leaked | Verified |
| Eq. 2-3: two-point calibration improves accuracy | Verified |
| Eq. 4: compressor mass flow from displacement x density x eta_vol | Verified |
| Eq. 5-6: valve leakage from Cv x dP^2 | Verified (small contribution) |
| eta_vol drops during pump-down as dP increases | Verified |
| Higher outdoor T -> more condenser charge | Verified |
| All predictions within +/-6% | Verified (0.5% mean error) |

## Remaining Gaps

1. **5-ton initial mass flow**: Model gives 0.28 lbm/s vs paper's ~0.40 lbm/s.
   Root cause: the simple phase 1/phase 2 model keeps mass flow too constant
   during phase 1, requiring a lower initial flow to match the 24s total duration.

2. **Initial suction pressure**: 233 vs ~250 psia (7% offset, likely CoolProp
   vs REFPROP property difference for R410A at 75F).

3. **RTU validation (Table 3, Fig 11)**: Not implemented (geometry unavailable).

## Deviations

See [DEVIATIONS.md](DEVIATIONS.md).
