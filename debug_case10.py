#!/usr/bin/env python3
"""
Diagnostic script: charge breakdown vs T_cond for the failing Case 10
(T_outdoor=79°F, target charge=4.132 kg = 9.11 lbm).

Sweeps T_cond from 100°F to 156°F in 10°F steps and prints the full
charge breakdown at each point, so we can see where the charge capacity
flattens out and what component is limiting.
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from pyhpdm.properties.refrigerant import (
    Refrigerant, F_to_K, K_to_F, Pa_to_psi, LBM_TO_KG,
)
from pyhpdm.components.compressor import CompressorMap
from pyhpdm.components.heat_exchanger.microchannel import (
    OUTDOOR_MCHX_SPLIT, solve_mchx_condenser,
)
from pyhpdm.solver.system import (
    charge_residual, SystemGeometry, _evaporator_charge,
)

# ---- Same setup as reproduce_paper.py ----

REFRIGERANT = "R410A"

COMPRESSOR_COEFFS_MDOT_LBM_H = [
    176.0, 2.72, -2.12, 0.0172, -0.0112, 0.0181,
    6.52e-5, 1.08e-5, 4.00e-5, -5.54e-5,
]
COMPRESSOR_COEFFS_POWER_W = [
    1590.0, 6.79, -34.9, -0.226, -0.0660, 0.388,
    -1.37e-5, 1.01e-3, 7.41e-4, -1.12e-3,
]
V_DISPLACEMENT = 0.000501302 * 0.0283168
N_RPM = 3600.0
V_AIR_FRONTAL = 0.45

ref = Refrigerant(REFRIGERANT)
compressor = CompressorMap(
    coeffs_mdot=COMPRESSOR_COEFFS_MDOT_LBM_H,
    coeffs_power=COMPRESSOR_COEFFS_POWER_W,
    V_displacement=V_DISPLACEMENT,
    N_rpm=N_RPM,
    refrigerant=REFRIGERANT,
    T_sh_rated_K=11.1,
    F_mass=0.75,
)
system_geom = SystemGeometry.paper_split_system()
condenser_geom = OUTDOOR_MCHX_SPLIT

# ---- Case 10 parameters ----
T_outdoor_F = 79.0
T_outdoor_K = F_to_K(T_outdoor_F)
T_indoor_K = F_to_K(80.0)
charge_target_kg = 9.11 * LBM_TO_KG  # 4.132 kg
superheat_K = 5.0
n_segments = 30

T_evap_K = T_indoor_K - 12.0
P_evap = ref.P_sat(T_evap_K)

T_crit = ref.T_crit
print(f"R410A critical temperature: {K_to_F(T_crit):.1f}°F ({T_crit:.2f} K)")
print(f"T_outdoor = {T_outdoor_F}°F ({T_outdoor_K:.2f} K)")
print(f"T_evap = {K_to_F(T_evap_K):.1f}°F, P_evap = {Pa_to_psi(P_evap):.1f} psi")
print(f"Target charge = {charge_target_kg:.3f} kg ({charge_target_kg/LBM_TO_KG:.2f} lbm)")
print()

# ---- Sweep T_cond ----
T_cond_F_values = np.arange(100.0, 158.0, 10.0)

header = (
    f"{'T_cond':>8} {'P_cond':>8} {'Subcool':>8} {'M_total':>8} "
    f"{'M_cond':>8} {'M_liqln':>8} {'M_evap':>8} {'M_suct':>8} "
    f"{'M_disch':>8} {'M_add':>8} {'rho_liq':>8} {'Residual':>9}"
)
units = (
    f"{'[°F]':>8} {'[psi]':>8} {'[K]':>8} {'[kg]':>8} "
    f"{'[kg]':>8} {'[kg]':>8} {'[kg]':>8} {'[kg]':>8} "
    f"{'[kg]':>8} {'[kg]':>8} {'[kg/m³]':>8} {'[kg]':>9}"
)
print(header)
print(units)
print("-" * len(header))

for Tc_F in T_cond_F_values:
    Tc_K = F_to_K(Tc_F)

    # Skip if above critical
    if Tc_K >= T_crit - 1.0:
        print(f"{Tc_F:>8.1f}  ** above critical, skipping **")
        continue

    P_cond = ref.P_sat(Tc_K)

    # Compressor operating point
    Te_F = K_to_F(T_evap_K)
    m_dot = compressor.mass_flow_kg_s(Te_F, Tc_F)
    T_dis, h_dis, _ = compressor.discharge_state(Te_F, Tc_F)

    # Condenser model
    cond_result = solve_mchx_condenser(
        T_ref_in=T_dis,
        P_cond=P_cond,
        m_dot_ref=m_dot,
        T_air_in=T_outdoor_K,
        V_air_frontal=V_AIR_FRONTAL,
        geom=condenser_geom,
        ref=ref,
        n_segments=n_segments,
    )

    M_condenser = cond_result.charge_total
    subcooling = cond_result.subcooling

    # Liquid line
    T_cond_exit = cond_result.T_ref_out
    T_sat = ref.T_sat(P_cond)
    T_liquid = min(T_cond_exit, T_sat - 0.5)
    rho_liquid = ref.rho(T_liquid, P_cond)
    M_liquid_line = rho_liquid * system_geom.V_liquid_line_m3

    # Suction line
    T_suction = T_evap_K + superheat_K
    rho_suction = ref.rho(T_suction, P_evap)
    M_suction_line = rho_suction * system_geom.V_suction_line_m3

    # Discharge line
    rho_discharge = ref.rho(T_dis, P_cond)
    M_discharge_line = rho_discharge * system_geom.V_discharge_line_m3

    # Evaporator
    M_evaporator = _evaporator_charge(
        P_evap,
        system_geom.V_evaporator_m3 + system_geom.V_additional_lp_m3,
        ref,
    )

    # Additional HP
    M_additional_hp = rho_liquid * system_geom.V_additional_hp_m3

    M_total = (M_condenser + M_liquid_line + M_suction_line
               + M_discharge_line + M_evaporator + M_additional_hp)
    residual = M_total - charge_target_kg

    print(
        f"{Tc_F:>8.1f} {Pa_to_psi(P_cond):>8.1f} {subcooling:>8.1f} "
        f"{M_total:>8.3f} {M_condenser:>8.3f} {M_liquid_line:>8.3f} "
        f"{M_evaporator:>8.4f} {M_suction_line:>8.4f} "
        f"{M_discharge_line:>8.4f} {M_additional_hp:>8.4f} "
        f"{rho_liquid:>8.1f} {residual:>+9.3f}"
    )

print()
print(f"Volume summary:")
print(f"  Liquid line:    {system_geom.V_liquid_line_m3*1e3:.3f} L")
print(f"  Suction line:   {system_geom.V_suction_line_m3*1e3:.3f} L")
print(f"  Discharge line: {system_geom.V_discharge_line_m3*1e3:.4f} L")
print(f"  Evaporator:     {system_geom.V_evaporator_m3*1e3:.3f} L")
print(f"  Additional HP:  {system_geom.V_additional_hp_m3*1e3:.3f} L")
print(f"  Additional LP:  {system_geom.V_additional_lp_m3*1e3:.3f} L")
