# Paper Audit: Li, Shen, Welch & Gluesenkamp (2024)
# "A Refrigerant Charge Prediction Method Based on Pump Down Operation"
# DOI: 10.18462/iir.gl2024.1298

## Equations

### Eq. (1) — Total charge decomposition
Charge = Charge_viaCompressor - Charge_viaFourWayValve + CondenserCharge_BeforePumpDown + LowPressureSideCharge_AfterPumpDown
- 4th term (LP vapor after pump-down) is negligible and neglected in practice.

### Eq. (2) — Charge calibration error term
ΔM_liqL = C + k_liqL × L_liq
- C, k_liqL: regression constants from two operating points
- L_liq: liquid coil length (percentage of total condenser length)
- Paper's regression for split system: DeltaCharge = 0.0367 * LiquidLength - 1.9154

### Eq. (3) — Corrected condenser charge
M_corrected,LiqL = M_simulated + ΔM_liqL

### Eq. (4) — Compressor mass flow rate
Mr_compressor = DisplacementVolume × ρ_suction × η_volumetric
- η_volumetric from AHRI 10-coefficient compressor map
- ρ_suction from refrigerant properties at (P_suction, T_suction)

### Eq. (5) — 4-way valve volumetric flow rate
VFR_4WayValve = Cv_fourWayValve × (P_discharge - P_suction)²
- Cv: regression constant for valve flow

### Eq. (6) — 4-way valve mass flow rate
Mr_4-wayValve = ρ_discharge × VFR_4-WayValve

## Key Unnumbered Equations

### AHRI 10-coefficient compressor map (from ORNL/CON-343 and ACEEE 2017)
Y = C1 + C2·Te + C3·Tc + C4·Te² + C5·Te·Tc + C6·Tc² + C7·Te³ + C8·Tc·Te² + C9·Te·Tc² + C10·Tc³
- Y = mass flow rate [lbm/h] or power [W]
- Te, Tc: evaporating and condensing saturation temperatures [°F]

### Volumetric efficiency (derived from map)
η_vol = ṁ_map / (V_displacement × ρ_suction × N_speed)

### Rouhani-Axelsson (1970) void fraction
α = (x/ρ_g) × { [1 + 0.12(1-x)] × [x/ρ_g + (1-x)/ρ_l] + 1.18(1-x)[gσ(ρ_l-ρ_g)]^0.25 / (G × ρ_l^0.5) }^(-1)

### Shen et al. (2009) two-point charge tuning
ΔM = C + k × L_liq
Fitted from two operating points; applied as additive correction to simulated condenser charge.

## Tables

### Table 1 — Microchannel HX dimensions (split system)
| Parameter                    | Indoor MCHX | Outdoor MCHX |
|------------------------------|-------------|--------------|
| Face area (m²)               | 0.58        | 2.09         |
| Total Tube Number            | 54          | 229          |
| Number of rows               | 1           | 1            |
| Fin density (fins/m)         | 787         | 630          |
| Tube width (m)               | 0.254       | 0.206        |
| Tube Height (m)              | 0.013       | 0.013        |
| Number of Microchannels      | 26          | 20           |
| Microchannel hydraulic dia (m)| 0.0068     | 0.0071       |

### Table 2 — Split system test matrix (cooling mode)
| Charge →          | 7 lbm (3.18 kg) | 8.08 lbm (3.67 kg) | 9.11 lbm (4.13 kg) |
|-------------------|------------------|---------------------|---------------------|
| Outdoor T         | 71°F (21.6°C)    | 71°F (21.6°C)       | 71°F (21.6°C)       |
|                   | 79°F (26.1°C)    | 79°F (26.1°C)       | 79°F (26.1°C)       |
|                   | 87°F (30.6°C)    | 87°F (30.6°C)       | NA                  |
|                   | 95°F (35°C)      | 95°F (35°C)         | NA                  |

### Table 3 — RTU test matrix (cooling mode)
| T_outdoor  | 8 lbm (3.63 kg) | 9 lbm (4.08 kg) | 10 lbm (4.54 kg) | 11 lbm (4.99 kg) |
|------------|------------------|------------------|-------------------|-------------------|
| 71°F       | √                | √                | √                 | √                 |
| 79°F       | √                | √                | √                 | √                 |
| 87°F       | √                | √                | √                 | √                 |
| 95°F       | √                | √                | √                 | √                 |

## Figures to Reproduce

| Fig | Description | Data needed | Priority |
|-----|-------------|-------------|----------|
| 2   | Charge error vs liquid coil length regression | Simulated condenser charges at multiple conditions | HIGH |
| 3   | Compressor η_vol during pump-down (71°F, 7 lbm) | Compressor map + pressure traces | HIGH |
| 4   | Refrigerant mass flow via compressor during pump-down | Same as Fig 3 | HIGH |
| 5   | Suction & discharge pressure during pump-down | Simulated or measured pressure traces | HIGH |
| 6   | Mass flow rate via 4-way valve | Valve model + pressures | MEDIUM |
| 8   | Pump-down duration vs outdoor T and charge | Full simulation sweep | MEDIUM |
| 9   | Predicted vs measured charge (split system, ±6%) | Full method validation | CRITICAL |
| 11  | Predicted vs actual charge (RTU, ±5%) | Full method validation | CRITICAL |

## Hyperparameters & Setup

- Refrigerant: R410A
- Systems: 3-ton residential split (MCHX), 4-ton commercial RTU
- Void fraction model: Rouhani & Axelsson (1970)
- Condenser model: HPDM segment-by-segment with ε-NTU
- Compressor model: AHRI 10-coefficient polynomial map
- Charge calibration: Two-point linear regression (Shen et al. 2009)
- Compressor displacement volume: NOT specified in paper (must obtain from HPDM)
- Valve Cv constant: NOT specified in paper (must fit or obtain)
- Compressor map coefficients: NOT specified (must obtain from HPDM for the specific units)
- Number of HX segments: NOT specified
- Time step for pump-down integration: NOT specified
- Low-pressure cutoff for pump-down termination: ~20 psi for R410A

## Missing Details (Gaps)

1. **Compressor map coefficients** — Paper does not publish the 10 coefficients for either system
2. **Valve Cv constant** — Not published; must be fitted from data
3. **Compressor displacement volume** — Not given for either compressor
4. **Number of condenser segments** — Not specified
5. **Pump-down time step** — Not specified
6. **Indoor conditions during pump-down** — Not explicitly stated
7. **Condenser fan operation during pump-down** — Fan appears to run (outdoor unit operates)
8. **RTU condenser geometry** — Not published (unlike split system Table 1)
9. **Initial steady-state operating conditions** — Not fully specified for each test point

## Claims to Verify

1. Split system charge prediction within 6% of actual (Fig 9)
2. RTU charge prediction within 5% of actual (Fig 11)
3. All pump-down operations complete within 100 seconds (Fig 8)
4. Calibration significantly improves charge prediction vs uncalibrated model
5. Method works across multiple charge levels and outdoor temperatures
