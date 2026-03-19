"""
Four-way valve leakage model during pump-down.

During pump-down, refrigerant leaks from the high-pressure (discharge) side
back to the low-pressure (suction) side through the 4-way reversing valve.
This leakage opposes the compressor's migration of charge.

=== Eq. (5) of Li & Shen (2024) ===
VFR_4WayValve = Cv × (P_discharge - P_suction)²

=== Eq. (6) of Li & Shen (2024) ===
Mr_4-wayValve = ρ_discharge × VFR_4WayValve

DEVIATION DEV-006: Cv value not published in paper. See DEVIATIONS.md.
"""
from ..properties.refrigerant import Refrigerant


def four_way_valve_leakage(P_discharge_Pa, P_suction_Pa, T_discharge_K,
                           Cv, refrigerant_obj):
    """Calculate mass flow rate through 4-way valve during pump-down.

    Parameters
    ----------
    P_discharge_Pa : float — discharge pressure [Pa]
    P_suction_Pa : float — suction pressure [Pa]
    T_discharge_K : float — discharge temperature [K]
    Cv : float — valve flow coefficient [m³/(s·Pa²)]
    refrigerant_obj : Refrigerant

    Returns
    -------
    m_dot_valve : float — mass flow rate through valve [kg/s] (positive = HP→LP)
    VFR : float — volumetric flow rate [m³/s]
    """
    delta_P = P_discharge_Pa - P_suction_Pa
    if delta_P <= 0:
        return 0.0, 0.0

    # === Eq. (5): VFR = Cv × (P_dis - P_suc)² ===
    VFR = Cv * delta_P**2

    # === Eq. (6): Mr = ρ_discharge × VFR ===
    rho_dis = refrigerant_obj.rho(T_discharge_K, P_discharge_Pa)
    m_dot_valve = rho_dis * VFR

    return m_dot_valve, VFR


def estimate_Cv_from_figure6(ref_name="R410A"):
    """Estimate Cv from Figure 6 of the paper.

    From Fig 6, at t≈25s (mid pump-down for 71°F, 7 lbm case):
      - Mr_4way ≈ 0.00025 lbm/s ≈ 1.134e-4 kg/s
      - From Fig 5: P_dis ≈ 290 psi ≈ 1999 kPa, P_suc ≈ 100 psi ≈ 689 kPa
      - ΔP ≈ 190 psi ≈ 1310 kPa = 1.31e6 Pa
      - ρ_discharge: at ~290 psi discharge, T_dis ≈ 60°C → superheated vapor
        ρ ≈ 80 kg/m³ (approximate)

    From Eq. (5)-(6):
      VFR = Mr / ρ_dis = 1.134e-4 / 80 ≈ 1.42e-6 m³/s
      Cv = VFR / ΔP² = 1.42e-6 / (1.31e6)² ≈ 8.3e-19 m³/(s·Pa²)

    This is a rough estimate. The Cv may need calibration.
    """
    return 8.3e-19  # m³/(s·Pa²) — rough estimate from Fig 6
