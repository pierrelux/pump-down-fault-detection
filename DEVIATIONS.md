# Deviations Log

Every deviation from the paper's method is logged here.

## DEV-001: CoolProp vs REFPROP for R410A properties
- **Paper uses:** HPDM's built-in properties (historically REFPROP-based)
- **We use:** CoolProp (open-source) for R410A as pseudo-pure fluid
- **Impact:** Minor. CoolProp gives P_sat(75F) = 233 psia vs paper's ~250 psia (7% offset).
  This propagates through all pressure values but does not affect the method structure.

## DEV-002: Compressor map coefficients from HPDM scrape
- **Paper uses:** Maps for the specific 3-ton and 4-ton units tested (not published)
- **We use:** AHRI 10-coefficient map scraped from the HPDM web interface
  (3600 RPM default compressor). Stored in `references/hpdm_scraped/compressor10_map.csv`.
- **Impact:** Moderate. The scraped map is for HPDM's default compressor, not the
  paper's exact unit. Mass flow and volumetric efficiency at any (Te, Tc) will differ.
  For the 3-ton validation (Fig 7), this works well (0.5% mean error). For the 5-ton
  simulation (Figs 8-10), see DEV-008.

## DEV-003: RTU condenser geometry not published
- **Paper uses:** A 4-ton RTU (Table 3, Figure 11)
- **We do:** Not implemented — geometry not available
- **Impact:** Table 3 / Figure 11 validation cannot be reproduced.

## DEV-004: Simulated vs experimental pump-down pressure traces
- **Paper uses:** Experimentally measured P_suction(t) and P_discharge(t)
- **We do:** Simulate the transient by modeling LP-side as a constant-volume two-phase
  reservoir (phase 1: liquid boil-off at constant P; phase 2: vapor evacuation with
  falling P). P_discharge is computed from a dynamic condenser approach temperature.
- **Impact:** Moderate. The simulation produces the correct qualitative shape (pressure
  plateau followed by sharp decline) and terminates at the cutoff pressure. The
  phase 1 / phase 2 transition is sharper than in reality, where the pressure
  decline is more gradual.

## DEV-005: Number of condenser segments
- **Paper uses:** HPDM's segment-by-segment model (count not specified)
- **We use:** 30 segments (set in `reproduce_paper.py`, `n_segments=30`)
- **Impact:** Minor. Charge inventory converges by ~15 segments.

## DEV-006: Valve Cv estimated from Figure 6
- **Paper uses:** A Cv constant for 4-way valve leakage (value not published)
- **We use:** Cv = 8.3e-19 m^3/(s*Pa^2), estimated from Fig 6 data points
  (see `pyhpdm/components/valve.py:estimate_Cv_from_figure6`)
- **Impact:** Minor. Valve leakage is ~2-3% of total charge migrated.

## DEV-007: Microchannel port diameter interpretation
- **Paper says:** Table 1 lists "Microchannel hydraulic diameter (m)" as 0.0068 (indoor)
  and 0.0071 (outdoor), which would be 6.8 and 7.1 mm
- **We interpret as:** 0.68 mm and 0.71 mm (likely a decimal place error in the paper).
  6.8-7.1 mm channels are not microchannels; typical Dh is 0.5-1.5 mm.
- **Impact:** Critical for condenser charge — internal volume scales directly with Dh^2.

## DEV-008: 5-ton compressor approximation (Figs 8-10)
- **Paper uses:** A ZP61 (5-ton) compressor with its own AHRI map
- **We use:** The 3-ton HPDM map (DEV-002) with coefficients multiplied by a calibrated
  scale factor (2.57x). The scale is found via `brentq` to match the 24s pump-down
  duration. The theoretical displacement ratio (3.91x) overshoots because the simple
  two-phase model doesn't capture the gradual mass-flow decrease seen in reality.
- **Impact:** Initial mass flow is 0.28 lbm/s vs paper's ~0.40 lbm/s. The overall
  duration and pressure endpoints match, but the time profile differs (constant flow
  during phase 1 vs the paper's gradual decline).

## DEV-009: LP volume and initial quality (Figs 8-10)
- **Paper uses:** LP volume derived from actual system geometry (not published)
- **We use:** V_LP = 10 L (nominal estimate for a 5-ton system) and x_initial = 0.2
  (initial two-phase quality). These are not calibrated; only the compressor scale
  is calibrated to match duration.
- **Impact:** Affects the phase 1/phase 2 split timing and the residual LP charge
  at termination.
