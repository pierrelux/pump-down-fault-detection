"""
Segment-by-segment heat exchanger model framework.

The HPDM models condensers and evaporators by dividing the heat exchanger
into N segments along the refrigerant flow path. Each segment uses the
ε-NTU method to compute heat transfer. The refrigerant state transitions
through three zones: superheated → two-phase → subcooled (condenser)
or two-phase → superheated (evaporator).

This module provides the ε-NTU calculation and the segment integration logic.

Reference: Flex HPDM General Introduction; ORNL/CON-343 Section on HX models.
"""
import numpy as np
from ...properties.refrigerant import Refrigerant
from .void_fraction import rouhani_axelsson, two_phase_density


def epsilon_NTU_crossflow(NTU, C_ratio, flow_arrangement="unmixed_unmixed"):
    """ε-NTU for crossflow heat exchanger (air-to-refrigerant).

    For the common case of air (unmixed) flowing over refrigerant tubes:
    - During two-phase: C_ratio → 0 (C_max = ∞), so ε = 1 - exp(-NTU)
    - During single-phase: use crossflow formula

    Parameters
    ----------
    NTU : float — number of transfer units
    C_ratio : float — C_min / C_max (0 ≤ C_ratio ≤ 1)
    flow_arrangement : str — "unmixed_unmixed" or "condensing"/"evaporating"

    Returns
    -------
    epsilon : float — heat exchanger effectiveness
    """
    if NTU < 1e-10:
        return 0.0

    if C_ratio < 1e-6:
        # Phase-change side has infinite capacity: ε = 1 - exp(-NTU)
        return 1.0 - np.exp(-NTU)

    if flow_arrangement == "unmixed_unmixed":
        # Crossflow, both streams unmixed (approximate Kays & London)
        exp_term = NTU**0.78 * C_ratio
        return 1.0 - np.exp((1.0 / C_ratio) * exp_term * (np.exp(-C_ratio * exp_term) - 1.0))
    elif flow_arrangement == "counterflow":
        if abs(C_ratio - 1.0) < 1e-6:
            return NTU / (1.0 + NTU)
        return (1.0 - np.exp(-NTU * (1.0 - C_ratio))) / (1.0 - C_ratio * np.exp(-NTU * (1.0 - C_ratio)))
    else:
        # Default: phase change (C_ratio = 0 effectively)
        return 1.0 - np.exp(-NTU)


class CondenserSegmentResult:
    """Results from a single condenser segment calculation."""
    def __init__(self):
        self.Q = 0.0            # heat transfer [W]
        self.T_ref_out = 0.0    # refrigerant outlet temperature [K]
        self.h_ref_out = 0.0    # refrigerant outlet enthalpy [J/kg]
        self.T_air_out = 0.0    # air outlet temperature [K]
        self.phase = ""         # "superheated", "two_phase", "subcooled"
        self.x_avg = 0.0        # average quality (for two-phase)
        self.charge = 0.0       # refrigerant mass in segment [kg]
        self.length_frac = 0.0  # fraction of total HX length


def solve_condenser_segment(
    # Refrigerant state at inlet
    T_ref_in, P_ref, h_ref_in, m_dot_ref,
    # Air state at inlet
    T_air_in, m_dot_air,
    # Geometry
    A_air, A_ref, A_cs_ref, segment_length,
    # Heat transfer coefficients
    h_air, h_ref,
    # Refrigerant object
    ref,
    # Air properties
    cp_air=1006.0,
):
    """Solve one condenser segment using ε-NTU.

    Parameters
    ----------
    T_ref_in : float — refrigerant inlet temperature [K]
    P_ref : float — refrigerant pressure [Pa] (assumed constant across segment)
    h_ref_in : float — refrigerant inlet enthalpy [J/kg]
    m_dot_ref : float — refrigerant mass flow rate [kg/s]
    T_air_in : float — air inlet temperature [K]
    m_dot_air : float — air mass flow rate [kg/s]
    A_air : float — air-side heat transfer area [m²]
    A_ref : float — refrigerant-side heat transfer area [m²]
    A_cs_ref : float — refrigerant flow cross-section area [m²]
    segment_length : float — segment length [m]
    h_air : float — air-side HTC [W/(m²·K)]
    h_ref : float — refrigerant-side HTC [W/(m²·K)]
    ref : Refrigerant
    cp_air : float — air specific heat [J/(kg·K)]

    Returns
    -------
    result : CondenserSegmentResult
    """
    result = CondenserSegmentResult()

    T_sat = ref.T_sat(P_ref)
    h_l = ref.h_sat_liquid(P_ref)
    h_g = ref.h_sat_vapor(P_ref)

    # Determine phase
    if h_ref_in > h_g:
        result.phase = "superheated"
    elif h_ref_in > h_l:
        result.phase = "two_phase"
    else:
        result.phase = "subcooled"

    # Overall UA
    if h_air < 1e-3 or h_ref < 1e-3:
        result.h_ref_out = h_ref_in
        result.T_ref_out = T_ref_in
        result.T_air_out = T_air_in
        return result

    UA = 1.0 / (1.0 / (h_air * A_air) + 1.0 / (h_ref * A_ref))

    # Capacity rates
    C_air = m_dot_air * cp_air  # [W/K]

    if result.phase == "two_phase":
        # During phase change, C_ref → ∞, so C_min = C_air
        C_min = C_air
        C_ratio = 0.0
        NTU = UA / C_min if C_min > 0 else 0.0
        epsilon = epsilon_NTU_crossflow(NTU, C_ratio)

        Q_max = C_air * (T_sat - T_air_in)
        Q = epsilon * Q_max

        # Check if we exit two-phase region in this segment
        Q_available = m_dot_ref * (h_ref_in - h_l)  # heat to condense to saturated liquid
        if Q > Q_available and Q_available > 0:
            Q = Q_available  # only partially condense

        h_ref_out = h_ref_in - Q / m_dot_ref if m_dot_ref > 0 else h_ref_in
        result.x_avg = max(0, min(1, ref.quality(0.5 * (h_ref_in + h_ref_out), P_ref)))

        # Charge calculation with void fraction
        rho_l = ref.rho_sat_liquid(P_ref)
        rho_g = ref.rho_sat_vapor(P_ref)
        sigma = ref.sigma_at_P(P_ref)
        G = m_dot_ref / A_cs_ref if A_cs_ref > 0 else 100.0
        alpha = rouhani_axelsson(result.x_avg, rho_l, rho_g, sigma, G)
        rho_tp = two_phase_density(alpha, rho_l, rho_g)
        result.charge = rho_tp * A_cs_ref * segment_length

        result.T_ref_out = T_sat
        result.h_ref_out = h_ref_out

    else:
        # Single-phase (superheated or subcooled)
        # Use enthalpy-based cp to avoid (T,P) near saturation dome issue
        # with pseudo-pure fluids like R410A.
        # cp ≈ dh/dT at constant P, estimated by finite difference in h-space
        dh = 500.0  # J/kg perturbation
        T_plus = ref.T_from_Ph(P_ref, h_ref_in + dh)
        T_minus = ref.T_from_Ph(P_ref, h_ref_in - dh)
        cp_ref = 2.0 * dh / max(T_plus - T_minus, 0.01)
        cp_ref = max(cp_ref, 500.0)  # sanity floor

        C_ref = m_dot_ref * cp_ref
        C_min = min(C_air, C_ref)
        C_max = max(C_air, C_ref)
        C_ratio = C_min / C_max if C_max > 0 else 0.0

        NTU = UA / C_min if C_min > 0 else 0.0
        epsilon = epsilon_NTU_crossflow(NTU, C_ratio)

        Q_max = C_min * (T_ref_in - T_air_in)
        Q = epsilon * Q_max

        h_ref_out = h_ref_in - Q / m_dot_ref if m_dot_ref > 0 else h_ref_in
        T_ref_out = ref.T_from_Ph(P_ref, h_ref_out)

        # Check for phase boundary crossing
        if result.phase == "superheated" and h_ref_out < h_g:
            h_ref_out = h_g  # stop at saturation
            Q = m_dot_ref * (h_ref_in - h_g)
            T_ref_out = T_sat

        # Charge: single-phase density via (P, H) to avoid near-saturation issues
        rho_avg = ref.rho_from_Ph(P_ref, 0.5 * (h_ref_in + h_ref_out))
        result.charge = rho_avg * A_cs_ref * segment_length

        result.T_ref_out = T_ref_out
        result.h_ref_out = h_ref_out

    result.Q = Q
    result.T_air_out = T_air_in + Q / C_air if C_air > 0 else T_air_in
    result.length_frac = 1.0  # will be adjusted by caller

    return result


class CondenserResult:
    """Aggregate results from full condenser calculation."""
    def __init__(self):
        self.Q_total = 0.0              # total heat transfer [W]
        self.charge_total = 0.0         # total refrigerant mass [kg]
        self.T_ref_out = 0.0            # refrigerant outlet temperature [K]
        self.h_ref_out = 0.0            # refrigerant outlet enthalpy [J/kg]
        self.T_air_out_avg = 0.0        # average air outlet temperature [K]
        self.subcooling = 0.0           # condenser subcooling [K]
        self.L_liquid_pct = 0.0         # liquid (subcooled) length as % of total
        self.L_two_phase_pct = 0.0      # two-phase length as % of total
        self.L_superheat_pct = 0.0      # superheated length as % of total
        self.segments = []              # per-segment results


def solve_condenser(
    # Operating conditions
    T_ref_in, P_cond, m_dot_ref,
    T_air_in, m_dot_air,
    # Geometry
    n_segments, total_length, A_air_total, A_ref_total, A_cs_ref,
    # Heat transfer coefficients (simplified: constant per zone)
    h_air, h_ref_sp, h_ref_tp,
    # Refrigerant
    ref,
    cp_air=1006.0,
):
    """Solve condenser segment-by-segment.

    Refrigerant enters as superheated vapor and exits as subcooled liquid.
    Segments are solved sequentially along the refrigerant flow path.
    Air flows in crossflow (each segment sees fresh air at T_air_in for
    a simple parallel-crossflow arrangement).

    Parameters
    ----------
    T_ref_in : float — inlet refrigerant temperature [K] (superheated)
    P_cond : float — condensing pressure [Pa]
    m_dot_ref : float — refrigerant mass flow rate [kg/s]
    T_air_in : float — inlet air temperature [K]
    m_dot_air : float — total air mass flow rate [kg/s]
    n_segments : int — number of segments
    total_length : float — total refrigerant-side tube length [m]
    A_air_total : float — total air-side area [m²]
    A_ref_total : float — total refrigerant-side area [m²]
    A_cs_ref : float — refrigerant flow cross-section area [m²]
    h_air : float — air-side HTC [W/(m²·K)]
    h_ref_sp : float — single-phase refrigerant HTC [W/(m²·K)]
    h_ref_tp : float — two-phase refrigerant HTC [W/(m²·K)]
    ref : Refrigerant

    Returns
    -------
    CondenserResult
    """
    cond = CondenserResult()

    seg_length = total_length / n_segments
    A_air_seg = A_air_total / n_segments
    A_ref_seg = A_ref_total / n_segments
    m_dot_air_seg = m_dot_air / n_segments  # air split equally across segments

    h_ref_in = ref.h(T_ref_in, P_cond)
    T_ref_current = T_ref_in
    h_ref_current = h_ref_in
    T_sat = ref.T_sat(P_cond)
    h_l = ref.h_sat_liquid(P_cond)
    h_g = ref.h_sat_vapor(P_cond)

    Q_total = 0.0
    charge_total = 0.0
    T_air_out_sum = 0.0
    n_superheat = 0
    n_two_phase = 0
    n_subcooled = 0

    for i in range(n_segments):
        # Determine HTC based on phase
        if h_ref_current > h_g:
            h_ref = h_ref_sp
        elif h_ref_current > h_l:
            h_ref = h_ref_tp
        else:
            h_ref = h_ref_sp

        seg = solve_condenser_segment(
            T_ref_current, P_cond, h_ref_current, m_dot_ref,
            T_air_in, m_dot_air_seg,
            A_air_seg, A_ref_seg, A_cs_ref, seg_length,
            h_air, h_ref,
            ref, cp_air,
        )

        # Count phases
        if seg.phase == "superheated":
            n_superheat += 1
        elif seg.phase == "two_phase":
            n_two_phase += 1
        else:
            n_subcooled += 1

        Q_total += seg.Q
        charge_total += seg.charge
        T_air_out_sum += seg.T_air_out

        T_ref_current = seg.T_ref_out
        h_ref_current = seg.h_ref_out

        cond.segments.append(seg)

    cond.Q_total = Q_total
    cond.charge_total = charge_total
    cond.T_ref_out = T_ref_current
    cond.h_ref_out = h_ref_current
    cond.T_air_out_avg = T_air_out_sum / n_segments
    cond.subcooling = T_sat - T_ref_current if T_ref_current < T_sat else 0.0

    cond.L_superheat_pct = 100.0 * n_superheat / n_segments
    cond.L_two_phase_pct = 100.0 * n_two_phase / n_segments
    cond.L_liquid_pct = 100.0 * n_subcooled / n_segments

    return cond
