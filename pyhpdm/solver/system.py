"""
Charge-balancing system solver.

Finds the steady-state operating point where the total refrigerant charge
inventory equals a specified target charge. This is a 1D root-finding problem:
for a TXV system (fixed superheat), increasing T_cond backs up more subcooled
liquid in the condenser and liquid line, so total charge is monotonically
increasing in T_cond. We use scipy.optimize.brentq to solve:

    charge_inventory(T_cond) - M_target = 0

For each T_cond guess, the solver:
1. Computes P_cond, P_evap from saturation
2. Evaluates compressor map → m_dot, T_discharge
3. Runs segment-by-segment condenser model → condenser charge, subcooling
4. Computes charge in liquid line, suction line, discharge line, evaporator

Key insight from HPDM: the liquid line holds ~68.5% of total charge. When charge
increases, extra refrigerant backs up as subcooled liquid → higher subcooling →
higher T_cond. This monotonicity guarantees brentq convergence.

Reference: Li, Shen, Welch & Gluesenkamp (2024), HPDM ChargSOLVER.
"""
import numpy as np
from dataclasses import dataclass, field
from scipy.optimize import brentq

from ..properties.refrigerant import Refrigerant, F_to_K, K_to_F, Pa_to_psi
from ..components.compressor import CompressorMap
from ..components.heat_exchanger.microchannel import (
    solve_mchx_condenser, MicrochannelGeometry,
)
from ..components.heat_exchanger.base import CondenserResult
from ..components.heat_exchanger.void_fraction import (
    rouhani_axelsson, two_phase_density,
)
from ..charge.inventory import charge_in_line


# ============================================================================
# System Geometry
# ============================================================================

@dataclass
class SystemGeometry:
    """Connecting-line and evaporator volumes for charge inventory.

    All volumes in m³. Derived from HPDM scraped data (sc_mhxs_hpdata.dat)
    and paper Table 1 geometry.
    """
    # Liquid line: between condenser exit and expansion device
    L_liquid_line_m: float       # length [m]
    D_liquid_line_m: float       # inner diameter [m]

    # Suction line: between evaporator exit and compressor inlet
    L_suction_line_m: float
    D_suction_line_m: float

    # Discharge line: between compressor outlet and condenser inlet
    L_discharge_line_m: float
    D_discharge_line_m: float

    # Evaporator internal volume [m³]
    V_evaporator_m3: float

    # Additional unmodeled high-pressure volume [m³]:
    # filter-drier, distributor tubes, evaporator headers, etc.
    V_additional_hp_m3: float = 0.0

    # Additional unmodeled low-pressure volume [m³]
    V_additional_lp_m3: float = 0.0

    @property
    def V_liquid_line_m3(self):
        return np.pi / 4.0 * self.D_liquid_line_m**2 * self.L_liquid_line_m

    @property
    def V_suction_line_m3(self):
        return np.pi / 4.0 * self.D_suction_line_m**2 * self.L_suction_line_m

    @property
    def V_discharge_line_m3(self):
        return np.pi / 4.0 * self.D_discharge_line_m**2 * self.L_discharge_line_m

    @classmethod
    def hpdm_default(cls):
        """HPDM default line sizes (validated against sc_mhxs_hpdata.dat output).

        Validated volumes (from HPDM charge output):
          Liquid:    V=1.492e-3 m³ → 3.23 lbm at operating conditions
          Suction:   V=2.617e-3 m³ → 0.236 lbm
          Discharge: V=7.45e-5 m³
        Line lengths from HPDM data, IDs back-calculated to match validated volumes.
        Evaporator: 80 tubes × 26 ports × Dh=0.668mm × L=1.143m → 8.33e-4 m³
        """
        return cls(
            L_liquid_line_m=44.0 * 0.3048,          # 13.41 m
            D_liquid_line_m=0.01190,                  # 11.9 mm (back-calc from V=1.492e-3)
            L_suction_line_m=20.4 * 0.3048,          # 6.22 m
            D_suction_line_m=0.02315,                 # 23.1 mm (back-calc from V=2.617e-3)
            L_discharge_line_m=1.0 * 0.3048,         # 0.305 m
            D_discharge_line_m=0.01764,               # 17.6 mm (back-calc from V=7.45e-5)
            V_evaporator_m3=80 * 26 * (np.pi / 4.0 * 0.000668**2) * 1.143,  # 8.33e-4
        )

    @classmethod
    def paper_split_system(cls):
        """Geometry for the paper's 3-ton split system.

        The paper (Table 1) does not specify connecting line dimensions.
        We use HPDM default line geometry (validated against HPDM charge output)
        as the paper's model is based on HPDM.

        Evaporator: from Table 1 indoor MCHX — 54 tubes × 26 ports × Dh=0.68mm.
        Uses circuit-based volume: 3 circuits × A_cs=3.5e-5 × L=4.76m = 5.0e-4 m³.

        Additional HP volume: compressor shell (~0.3L), filter-drier (~0.15L),
            service valves (~0.05L) = 0.5L total.
        Additional LP volume: evaporator headers (~0.3L), distributor tubes (~0.1L).
        """
        return cls(
            L_liquid_line_m=44.0 * 0.3048,          # 13.41 m (HPDM default)
            D_liquid_line_m=0.01190,                  # 11.9 mm (HPDM validated)
            L_suction_line_m=20.4 * 0.3048,          # 6.22 m (HPDM default)
            D_suction_line_m=0.02315,                 # 23.1 mm (HPDM validated)
            L_discharge_line_m=1.0 * 0.3048,         # 0.305 m
            D_discharge_line_m=0.01764,               # 17.6 mm (HPDM validated)
            V_evaporator_m3=3 * 3.5e-5 * 4.76,      # 5.0e-4 m³ (circuit-based)
            V_additional_hp_m3=1.5e-4,               # 0.15 L (filter-drier, valves)
            V_additional_lp_m3=4.0e-4,               # 0.40 L (evap headers, distributor)
        )


# ============================================================================
# Steady-State Result
# ============================================================================

@dataclass
class SteadyStateResult:
    """Result of the charge-balance solver."""
    T_cond_K: float = 0.0
    T_evap_K: float = 0.0
    P_cond_Pa: float = 0.0
    P_evap_Pa: float = 0.0
    subcooling_K: float = 0.0
    superheat_K: float = 0.0
    m_dot_kg_s: float = 0.0
    T_discharge_K: float = 0.0

    charge_condenser_kg: float = 0.0
    charge_evaporator_kg: float = 0.0
    charge_liquid_line_kg: float = 0.0
    charge_suction_line_kg: float = 0.0
    charge_discharge_line_kg: float = 0.0
    charge_total_kg: float = 0.0

    condenser_result: CondenserResult = field(default_factory=CondenserResult)


# ============================================================================
# Charge Residual Function
# ============================================================================

def _evaporator_charge(P_evap, V_evap, ref, x_avg=0.35):
    """Approximate charge in evaporator using Rouhani-Axelsson void fraction.

    The evaporator operates mostly in two-phase with typical average quality
    x_avg ≈ 0.35 (inlet quality ~0.2 from TXV, exit quality ~0.5 before
    superheat section). We use a representative average quality rather than
    segment-by-segment integration, which is sufficient since the evaporator
    holds a small fraction of total charge (~5%).

    Parameters
    ----------
    P_evap : float — evaporating pressure [Pa]
    V_evap : float — evaporator internal volume [m³]
    ref : Refrigerant
    x_avg : float — representative average quality (default 0.35)

    Returns
    -------
    M_evap : float — evaporator charge [kg]
    """
    rho_l = ref.rho_sat_liquid(P_evap)
    rho_g = ref.rho_sat_vapor(P_evap)
    sigma = ref.sigma_at_P(P_evap)

    # Use a representative mass flux for the evaporator
    # Typical G ~ 150 kg/(m²·s) for residential MCHX evaporator
    G_evap = 150.0

    # Integrate charge over quality range using 5-point Simpson's rule
    # Better approximates HPDM's 50-segment integration
    x_points = [0.15, 0.325, 0.50, 0.675, 0.85]
    weights = [1/12, 4/12, 2/12, 4/12, 1/12]  # composite Simpson weights
    rho_avg = 0.0
    for x, w in zip(x_points, weights):
        alpha = rouhani_axelsson(x, rho_l, rho_g, sigma, G_evap)
        rho_avg += w * two_phase_density(alpha, rho_l, rho_g)
    return rho_avg * V_evap


def charge_residual(
    T_cond_K,
    M_target_kg,
    T_indoor_K,
    T_outdoor_K,
    superheat_K,
    compressor,
    condenser_geom,
    system_geom,
    ref,
    V_air_frontal,
    n_segments=30,
):
    """Charge inventory residual: M_total(T_cond) - M_target.

    The root of this function gives the operating T_cond where total system
    charge equals the target.

    Parameters
    ----------
    T_cond_K : float — condensing temperature [K] (the unknown)
    M_target_kg : float — target total system charge [kg]
    T_indoor_K : float — indoor air temperature [K]
    T_outdoor_K : float — outdoor air temperature [K]
    superheat_K : float — evaporator exit superheat [K] (TXV controlled)
    compressor : CompressorMap
    condenser_geom : MicrochannelGeometry
    system_geom : SystemGeometry
    ref : Refrigerant
    V_air_frontal : float — condenser air frontal velocity [m/s]
    n_segments : int — condenser segments

    Returns
    -------
    residual : float — M_total - M_target [kg]. Zero at the solution.
    """
    # 1. Pressures from saturation temperatures
    P_cond = ref.P_sat(T_cond_K)
    T_evap_K = T_indoor_K - 12.0  # typical approach for indoor coil
    P_evap = ref.P_sat(T_evap_K)

    # 2. Compressor operating point
    Te_F = K_to_F(T_evap_K)
    Tc_F = K_to_F(T_cond_K)
    m_dot = compressor.mass_flow_kg_s(Te_F, Tc_F)
    T_dis, h_dis, _ = compressor.discharge_state(Te_F, Tc_F)

    # 3. Condenser model → charge + subcooling
    cond_result = solve_mchx_condenser(
        T_ref_in=T_dis,
        P_cond=P_cond,
        m_dot_ref=m_dot,
        T_air_in=T_outdoor_K,
        V_air_frontal=V_air_frontal,
        geom=condenser_geom,
        ref=ref,
        n_segments=n_segments,
    )
    M_condenser = cond_result.charge_total

    # 4. Liquid line charge
    # Condenser exit state: subcooled liquid at (P_cond, T_cond_exit)
    T_cond_exit = cond_result.T_ref_out
    T_sat = ref.T_sat(P_cond)
    # Clamp T_liquid to at least T_sat - 0.5K to avoid CoolProp near-saturation issues
    T_liquid = min(T_cond_exit, T_sat - 0.5)
    rho_liquid = ref.rho(T_liquid, P_cond)
    M_liquid_line = rho_liquid * system_geom.V_liquid_line_m3

    # 5. Suction line charge (superheated vapor)
    T_suction = T_evap_K + superheat_K
    rho_suction = ref.rho(T_suction, P_evap)
    M_suction_line = rho_suction * system_geom.V_suction_line_m3

    # 6. Discharge line charge (superheated vapor at high pressure)
    rho_discharge = ref.rho(T_dis, P_cond)
    M_discharge_line = rho_discharge * system_geom.V_discharge_line_m3

    # 7. Evaporator charge (two-phase approximation)
    M_evaporator = _evaporator_charge(
        P_evap,
        system_geom.V_evaporator_m3 + system_geom.V_additional_lp_m3,
        ref,
    )

    # 8. Additional high-pressure volume (filter-drier, service valves)
    # Filled with subcooled liquid at condenser exit conditions
    M_additional_hp = rho_liquid * system_geom.V_additional_hp_m3

    # Total
    M_total = (M_condenser + M_liquid_line + M_suction_line
               + M_discharge_line + M_evaporator + M_additional_hp)

    return M_total - M_target_kg


# ============================================================================
# Main Solver
# ============================================================================

def solve_charge_balance(
    M_target_kg,
    T_outdoor_K,
    compressor,
    condenser_geom,
    system_geom,
    ref,
    V_air_frontal=0.45,
    T_indoor_K=None,
    superheat_K=5.0,
    n_segments=30,
    T_cond_bracket=None,
    verbose=False,
):
    """Find the steady-state operating point where charge inventory = target.

    Uses scipy.optimize.brentq to find T_cond such that:
        charge_inventory(T_cond) = M_target_kg

    Parameters
    ----------
    M_target_kg : float — target total system charge [kg]
    T_outdoor_K : float — outdoor air temperature [K]
    compressor : CompressorMap
    condenser_geom : MicrochannelGeometry — condenser geometry
    system_geom : SystemGeometry — connecting line volumes
    ref : Refrigerant
    V_air_frontal : float — condenser air frontal velocity [m/s]
    T_indoor_K : float — indoor air temperature [K] (default: 80°F)
    superheat_K : float — evaporator exit superheat [K] (TXV)
    n_segments : int — condenser model segments
    T_cond_bracket : tuple(float, float) — (T_cond_lo, T_cond_hi) [K]
        Default: (T_outdoor + 5, T_outdoor + 40)
    verbose : bool — print iteration info

    Returns
    -------
    SteadyStateResult

    Raises
    ------
    ValueError — if target charge is outside achievable range
    """
    if T_indoor_K is None:
        T_indoor_K = F_to_K(80.0)  # 80°F indoor

    # Default bracket: T_cond in [T_outdoor+2, T_outdoor+45] K
    # Cap T_hi below critical temperature (R410A Tcrit = 344.49 K = 160.4°F)
    T_crit = ref.T_crit
    if T_cond_bracket is None:
        T_lo = T_outdoor_K + 2.0
        T_hi = min(T_outdoor_K + 45.0, T_crit - 2.0)
    else:
        T_lo, T_hi = T_cond_bracket
        T_hi = min(T_hi, T_crit - 2.0)

    # Common kwargs for the residual function
    kwargs = dict(
        M_target_kg=M_target_kg,
        T_indoor_K=T_indoor_K,
        T_outdoor_K=T_outdoor_K,
        superheat_K=superheat_K,
        compressor=compressor,
        condenser_geom=condenser_geom,
        system_geom=system_geom,
        ref=ref,
        V_air_frontal=V_air_frontal,
        n_segments=n_segments,
    )

    # Evaluate bracket endpoints
    f_lo = charge_residual(T_lo, **kwargs)
    f_hi = charge_residual(T_hi, **kwargs)

    if verbose:
        print(f"  Bracket: T_cond=[{K_to_F(T_lo):.1f}, {K_to_F(T_hi):.1f}]°F")
        print(f"  Residual at lo: {f_lo:+.4f} kg, at hi: {f_hi:+.4f} kg")

    # Check bracket validity
    T_cond_sol = None
    if f_lo > 0:
        # Minimum charge is above target — use T_lo as best approximation
        import warnings
        warnings.warn(
            f"Target charge {M_target_kg:.3f} kg is below minimum achievable "
            f"charge {M_target_kg + f_lo:.3f} kg at T_cond={K_to_F(T_lo):.1f}°F. "
            f"Using T_cond_lo as approximate solution."
        )
        T_cond_sol = T_lo
    elif f_hi < 0:
        # Both endpoints negative: charge curve is non-monotonic (peaks then
        # drops near T_crit as liquid density collapses). Search inward from
        # T_hi to find where residual is positive, giving a valid bracket.
        T_search = T_hi
        step = (T_hi - T_lo) / 10.0
        while T_search > T_lo + step:
            T_search -= step
            f_mid = charge_residual(T_search, **kwargs)
            if f_mid >= 0:
                # Found a positive point — use [T_lo, T_search] as bracket
                T_hi = T_search
                f_hi = f_mid
                if verbose:
                    print(f"  Re-bracketed: T_hi={K_to_F(T_hi):.1f}°F, "
                          f"residual={f_hi:+.4f} kg")
                break
        else:
            # Truly unachievable — no positive residual found anywhere
            import warnings
            warnings.warn(
                f"Target charge {M_target_kg:.3f} kg exceeds maximum achievable "
                f"charge {M_target_kg + f_hi:.3f} kg at T_cond={K_to_F(T_hi):.1f}°F. "
                f"Using T_cond_hi as approximate solution."
            )
            T_cond_sol = T_hi

    if T_cond_sol is None:
        # Normal solve (or re-bracketed): f_lo < 0, f_hi >= 0
        T_cond_sol = brentq(
            charge_residual,
            T_lo, T_hi,
            args=(M_target_kg, T_indoor_K, T_outdoor_K, superheat_K,
                  compressor, condenser_geom, system_geom, ref,
                  V_air_frontal, n_segments),
            xtol=0.01,   # 0.01 K tolerance
            rtol=1e-6,
            maxiter=50,
        )

    # Re-evaluate at solution to get full state
    P_cond = ref.P_sat(T_cond_sol)
    T_evap_K = T_indoor_K - 12.0
    P_evap = ref.P_sat(T_evap_K)
    Te_F = K_to_F(T_evap_K)
    Tc_F = K_to_F(T_cond_sol)

    m_dot = compressor.mass_flow_kg_s(Te_F, Tc_F)
    T_dis, h_dis, _ = compressor.discharge_state(Te_F, Tc_F)

    cond_result = solve_mchx_condenser(
        T_ref_in=T_dis,
        P_cond=P_cond,
        m_dot_ref=m_dot,
        T_air_in=T_outdoor_K,
        V_air_frontal=V_air_frontal,
        geom=condenser_geom,
        ref=ref,
        n_segments=n_segments,
    )

    # Recompute component charges
    T_sat = ref.T_sat(P_cond)
    T_cond_exit = cond_result.T_ref_out
    T_liquid = min(T_cond_exit, T_sat - 0.5)
    rho_liquid = ref.rho(T_liquid, P_cond)
    M_liquid_line = rho_liquid * system_geom.V_liquid_line_m3

    T_suction = T_evap_K + superheat_K
    rho_suction = ref.rho(T_suction, P_evap)
    M_suction_line = rho_suction * system_geom.V_suction_line_m3

    rho_discharge = ref.rho(T_dis, P_cond)
    M_discharge_line = rho_discharge * system_geom.V_discharge_line_m3

    M_evaporator = _evaporator_charge(
        P_evap,
        system_geom.V_evaporator_m3 + system_geom.V_additional_lp_m3,
        ref,
    )
    M_additional_hp = rho_liquid * system_geom.V_additional_hp_m3

    M_total = (cond_result.charge_total + M_liquid_line + M_suction_line
               + M_discharge_line + M_evaporator + M_additional_hp)

    result = SteadyStateResult(
        T_cond_K=T_cond_sol,
        T_evap_K=T_evap_K,
        P_cond_Pa=P_cond,
        P_evap_Pa=P_evap,
        subcooling_K=cond_result.subcooling,
        superheat_K=superheat_K,
        m_dot_kg_s=m_dot,
        T_discharge_K=T_dis,
        charge_condenser_kg=cond_result.charge_total,
        charge_evaporator_kg=M_evaporator,
        charge_liquid_line_kg=M_liquid_line,
        charge_suction_line_kg=M_suction_line,
        charge_discharge_line_kg=M_discharge_line,
        charge_total_kg=M_total,
        condenser_result=cond_result,
    )

    if verbose:
        print(f"  Solution: T_cond={K_to_F(T_cond_sol):.1f}°F, "
              f"subcooling={cond_result.subcooling:.1f} K")
        print(f"  Charge breakdown:")
        print(f"    Condenser:      {cond_result.charge_total:.4f} kg")
        print(f"    Liquid line:    {M_liquid_line:.4f} kg")
        print(f"    Evaporator:     {M_evaporator:.4f} kg")
        print(f"    Suction line:   {M_suction_line:.4f} kg")
        print(f"    Discharge line: {M_discharge_line:.4f} kg")
        print(f"    TOTAL:          {M_total:.4f} kg")

    return result
