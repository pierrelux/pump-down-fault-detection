# Math-to-Code Mapping

## Notation Table
| Paper symbol | Code name | Units | Description |
|-------------|-----------|-------|-------------|
| Te | T_evap | °F (AHRI) or K | Evaporating saturation temperature |
| Tc | T_cond | °F (AHRI) or K | Condensing saturation temperature |
| ṁ, Mr | m_dot | kg/s | Refrigerant mass flow rate |
| P | P_comp | W | Compressor power |
| η_vol | eta_vol | - | Compressor volumetric efficiency |
| η_isen | eta_isen | - | Compressor isentropic efficiency |
| V_disp | V_displacement | m³ | Compressor displacement volume |
| ρ | rho | kg/m³ | Refrigerant density |
| h | h | J/kg | Specific enthalpy |
| s | s | J/(kg·K) | Specific entropy |
| x | x, quality | - | Vapor quality (0=liquid, 1=vapor) |
| α | alpha, void_frac | - | Void fraction |
| ΔM | delta_M | kg | Charge correction term |
| C | C_cal | kg | Calibration intercept |
| k_liqL | k_cal | kg/% | Calibration slope |
| L_liq | L_liquid_pct | % | Liquid coil length as % of total |
| Cv | Cv_valve | m³/(s·Pa²) | Valve flow coefficient |
| VFR | VFR | m³/s | Volumetric flow rate through valve |
| G | G_mass_flux | kg/(m²·s) | Mass flux |
| σ | sigma | N/m | Surface tension |
| T_sc | T_subcooling | K | Condenser subcooling |
| T_sh | T_superheat | K | Evaporator superheat |

## Eq. (1) → pump_down.py: total_charge()
```
total_charge = charge_via_compressor - charge_via_4way_valve + condenser_charge_static
```
- charge_via_compressor = ∫₀ᵗ Mr_compressor(t) dt  (numerical integration)
- charge_via_4way_valve = ∫₀ᵗ Mr_4way(t) dt
- condenser_charge_static = from HX model + calibration

## Eq. (2)-(3) → charge/tuning.py: calibrate_charge()
```
delta_M = C_cal + k_cal * L_liquid_pct
M_corrected = M_simulated + delta_M
```
- L_liquid_pct: from HX model output (length of subcooled region / total length × 100)

## Eq. (4) → components/compressor.py: mass_flow_rate()
```
m_dot = V_displacement * rho_suction * eta_vol
```
- rho_suction = CoolProp(P_suction, T_suction) → density
- eta_vol = from AHRI map or from efficiency model

## Eq. (5)-(6) → components/valve.py: four_way_valve_leakage()
```
VFR = Cv_valve * (P_discharge - P_suction)**2
m_dot_valve = rho_discharge * VFR
```
- rho_discharge = CoolProp(P_discharge, T_discharge) → density

## Rouhani-Axelsson → components/heat_exchanger/void_fraction.py: rouhani_axelsson()
```
alpha = (x/rho_g) * inv
where inv = ([1 + 0.12*(1-x)] * [x/rho_g + (1-x)/rho_l]
             + 1.18*(1-x) * (g*sigma*(rho_l - rho_g))**0.25 / (G * rho_l**0.5))
alpha = (x/rho_g) / inv
```

## AHRI 10-coeff map → components/compressor.py: ahri_10_coeff()
```
Y = C[0] + C[1]*Te + C[2]*Tc + C[3]*Te**2 + C[4]*Te*Tc
  + C[5]*Tc**2 + C[6]*Te**3 + C[7]*Tc*Te**2 + C[8]*Te*Tc**2 + C[9]*Tc**3
```
- Te, Tc in °F per AHRI convention
- Y = mass_flow [lbm/h] or power [W] depending on coefficient set
