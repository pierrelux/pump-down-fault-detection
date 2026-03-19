"""
Microchannel heat exchanger model.

The residential split system in Li & Shen (2024) uses microchannel heat
exchangers (MCHX) for both indoor (evaporator) and outdoor (condenser).
Table 1 of the paper provides the geometry.

MCHX structure:
  - Flat tubes with multiple parallel microchannels (ports)
  - Louvered fins between flat tubes
  - Single-row arrangement (typical for MCHX)
  - Refrigerant flows through the microchannels inside the flat tubes

Geometry mapping:
  - D_h = microchannel hydraulic diameter
  - A_cs = N_tubes * N_ports * (π/4 * D_h²)  per circuit
  - A_ref = N_tubes * N_ports * (π * D_h * L_tube)  total
  - A_air = face_area * fin_density * ... (louvered fin area)
"""
import numpy as np
from .base import solve_condenser, CondenserResult
from ...properties.refrigerant import Refrigerant


class MicrochannelGeometry:
    """Geometry of a microchannel heat exchanger.

    From Table 1 of Li & Shen (2024).
    """
    def __init__(
        self,
        face_area,          # m² — frontal face area
        n_tubes,            # total number of flat tubes
        n_rows,             # number of tube rows (typically 1 for MCHX)
        fin_density,        # fins/m
        tube_width,         # m — width of flat tube (along air flow direction)
        tube_height,        # m — height of flat tube
        n_ports,            # number of microchannels per tube
        D_h_port,           # m — hydraulic diameter of each port
        n_circuits=1,       # number of parallel refrigerant circuits
        tube_length=None,   # m — length of each tube (if not derived from face_area)
    ):
        self.face_area = face_area
        self.n_tubes = n_tubes
        self.n_rows = n_rows
        self.fin_density = fin_density
        self.tube_width = tube_width
        self.tube_height = tube_height
        self.n_ports = n_ports
        self.D_h_port = D_h_port
        self.n_circuits = n_circuits

        # Derived geometry
        if tube_length is not None:
            self.tube_length = tube_length
        else:
            # Estimate tube length from face area and number of tubes
            # face_area ≈ n_tubes * tube_pitch * tube_length
            # tube_pitch ≈ tube_height + fin gap
            tube_pitch = self.tube_height + 0.001  # approximate 1mm fin gap
            self.tube_length = face_area / (n_tubes * tube_pitch) if n_tubes > 0 else 0.5

        # Port cross-section area (circular approximation)
        self.A_port = np.pi / 4.0 * D_h_port**2

        # Total flow cross-section per circuit
        tubes_per_circuit = n_tubes // max(n_circuits, 1)
        self.A_cs_circuit = tubes_per_circuit * n_ports * self.A_port

        # Total refrigerant-side surface area
        # Perimeter per port × length × number of ports × number of tubes
        self.A_ref_total = (np.pi * D_h_port * self.tube_length
                           * n_ports * n_tubes)

        # Total refrigerant flow length (per circuit)
        # In MCHX, tubes within a circuit are connected in PARALLEL by headers,
        # NOT in series. The refrigerant path length = tube_length × n_rows (passes).
        # tubes_per_circuit are all in parallel.
        self.L_ref_circuit = self.tube_length * n_rows
        self.tubes_per_circuit = tubes_per_circuit

        # Air-side area (approximate: face area × 2 sides × fin density × tube_width)
        # More precise calculation requires fin geometry details
        fin_pitch = 1.0 / fin_density if fin_density > 0 else 0.002
        fin_thickness = 0.0001  # 0.1 mm typical
        # Fin area ≈ 2 * tube_width * tube_length * n_tubes * fin_density * tube_pitch
        tube_pitch = self.tube_height + 0.001
        n_fins = int(self.tube_length * fin_density)
        A_fin = 2.0 * tube_width * tube_pitch * n_fins * n_tubes
        # Tube primary area (between fins)
        A_prime = 2.0 * tube_width * self.tube_length * n_tubes * (1 - fin_thickness * fin_density)
        self.A_air_total = A_fin + A_prime


# === Geometry definitions ===

# --------------------------------------------------------------------------
# HPDM_DEFAULT_OUTDOOR: 65-tube condenser from HPDM defaults.
# For validation against HPDM simulation output.
# --------------------------------------------------------------------------
# Geometry scraped from HPDM web interface:
#   Port Count: 14 holes per microchannel tube
#   Hydraulic Diameter: 0.0315 in = 0.0008001 m
#   Tube Width: 0.629 in = 0.01598 m (depth along air flow)
#   Tube Height: 0.088 in = 0.002235 m
#   Tube Length: 46.67 in = 1.185 m
#   Fin Density: 216 per foot = 708.7 per meter
#   Pass Number: 2 (47 + 18 tube distribution)
#   n_tubes = 65
_HPDM_D_h = 0.0315 * 0.0254              # 0.0008001 m
_HPDM_tube_length = 46.67 * 0.0254        # 1.185 m
_HPDM_tube_pitch = 0.375 * 0.0254         # 0.009525 m (for face area)

HPDM_DEFAULT_OUTDOOR = MicrochannelGeometry(
    face_area=65 * _HPDM_tube_pitch * _HPDM_tube_length,  # 0.734 m²
    n_tubes=65,
    n_rows=1,
    fin_density=216.0 / 0.3048,            # 708.7 fins/m
    tube_width=0.629 * 0.0254,             # 0.01598 m
    tube_height=0.088 * 0.0254,            # 0.002235 m
    n_ports=14,
    D_h_port=_HPDM_D_h,                   # 0.0008001 m
    n_circuits=2,                           # HPDM "Pass Number: 2"
    tube_length=_HPDM_tube_length,         # 1.185 m
)
# For the 2-pass HPDM condenser (47+18 tube distribution):
#   L_ref_circuit = 2 passes * tube_length = 2.37 m
#   A_cs_circuit = avg tubes_per_pass * n_ports * A_port
#     = ((47+18)/2) * 14 * pi/4 * 0.0008^2 = 32.5 * 14 * 5.027e-7 = 2.29e-4 m²
# Internal volume = 65 * 14 * pi/4 * 0.0008^2 * 1.185 = 5.42e-4 m³ = 0.542 L
_A_port_hpdm = np.pi / 4.0 * _HPDM_D_h**2
HPDM_DEFAULT_OUTDOOR.L_ref_circuit = 2.0 * _HPDM_tube_length          # 2.37 m
HPDM_DEFAULT_OUTDOOR.A_cs_circuit = ((47 + 18) / 2.0) * 14 * _A_port_hpdm  # 2.29e-4 m²

# --------------------------------------------------------------------------
# PAPER_SPLIT_OUTDOOR: 229-tube condenser from the paper's Table 1.
# Uses Table 1 values: N_port=20, D_h=0.8mm (HPDM-validated port diameter).
# --------------------------------------------------------------------------
# face_area = 2.09 m² (Table 1)
# n_tubes = 229, tube_height ≈ 0.013 m, tube_pitch ≈ 0.014 m
# → tube_length = 2.09 / (229 * 0.014) = 0.652 m
# 4 circuits, 2 passes each:
#   tubes_per_pass_per_circuit ≈ 229 / (4 * 2) = 28.6
#   L_ref_circuit = 2 * 0.652 = 1.304 m
#   A_cs_circuit ≈ 28.6 * 20 * pi/4 * 0.0008^2 = 2.88e-4 m²
# Internal volume = 229 * 20 * pi/4 * 0.0008^2 * 0.652 = 1.50e-3 m³ = 1.50 L
_PAPER_N_PORTS = 20  # from Table 1
_PAPER_D_H = 0.0008  # m — 0.8 mm (HPDM validated)
_PAPER_tube_length = 2.09 / (229 * 0.014)  # 0.652 m
_A_port_paper = np.pi / 4.0 * _PAPER_D_H**2

PAPER_SPLIT_OUTDOOR = MicrochannelGeometry(
    face_area=2.09,           # m² — from Table 1
    n_tubes=229,              # from Table 1
    n_rows=1,                 # from Table 1
    fin_density=630,          # fins/m — from Table 1
    tube_width=0.206,         # m — from Table 1 (depth along air flow)
    tube_height=0.013,        # m — from Table 1
    n_ports=_PAPER_N_PORTS,   # from Table 1 (20 ports/tube)
    D_h_port=_PAPER_D_H,     # m — 0.8 mm from HPDM
    n_circuits=4,             # typical for 3-ton outdoor unit
    tube_length=_PAPER_tube_length,  # 0.652 m
)
# Override with multi-pass geometry:
#   L_ref_circuit = 2 passes × tube_length = 1.304 m
#   A_cs_circuit = avg tubes_per_pass_per_circuit × n_ports × A_port
PAPER_SPLIT_OUTDOOR.L_ref_circuit = 2.0 * _PAPER_tube_length           # 1.304 m
PAPER_SPLIT_OUTDOOR.A_cs_circuit = (229.0 / (4 * 2)) * _PAPER_N_PORTS * _A_port_paper  # 2.88e-4 m²

# Header volume: MCHX headers (inlet/outlet manifolds) add significant volume.
# 229-tube condenser has large manifolds: ~25mm × 15mm cross-section,
# tube_length long, 2 headers per pass, 2 passes + intermediate distributors
# V_header = 4 × 3.75e-4 m² × 0.652 m = 9.8e-4 m³ ≈ 1.0 L
PAPER_SPLIT_OUTDOOR.V_header_m3 = 4 * 3.75e-4 * _PAPER_tube_length  # 9.8e-4 m³

# Default outdoor geometry used in reproduce_paper.py
OUTDOOR_MCHX_SPLIT = PAPER_SPLIT_OUTDOOR

INDOOR_MCHX_SPLIT = MicrochannelGeometry(
    face_area=0.58,           # m²
    n_tubes=54,
    n_rows=1,
    fin_density=787,          # fins/m
    tube_width=0.254,         # m
    tube_height=0.013,        # m
    n_ports=26,               # from Table 1
    D_h_port=0.00068,         # m — 0.68 mm port diameter (corrected)
    n_circuits=3,             # typical for 3-ton indoor unit
)
INDOOR_MCHX_SPLIT.A_cs_circuit = 3.5e-5
INDOOR_MCHX_SPLIT.L_ref_circuit = 4.76  # V_total ≈ 3×3.5e-5×4.76 = 0.5 L


def estimate_htc_microchannel_condensation(G, x, D_h, P, ref):
    """Estimate two-phase condensation HTC in microchannel.

    Simplified Shah (1979) correlation adapted for microchannels.
    This is a simplified version; the actual HPDM may use Kim & Mudawar (2013).

    Returns h [W/(m²·K)]
    """
    rho_l = ref.rho_sat_liquid(P)
    rho_g = ref.rho_sat_vapor(P)
    mu_l = ref.mu_sat_liquid(P)
    k_l = ref.k_sat_liquid(P)
    cp_l = ref.cp_sat_liquid(P)

    # Prandtl number
    Pr_l = mu_l * cp_l / k_l

    # Liquid-only Reynolds number
    Re_lo = G * D_h / mu_l

    # Single-phase liquid Nusselt (Dittus-Boelter)
    h_lo = 0.023 * Re_lo**0.8 * Pr_l**0.4 * k_l / D_h

    # Shah correlation for condensation
    # h_tp = h_lo × [(1-x)^0.8 + 3.8 × x^0.76 × (1-x)^0.04 / Pr^0.38]
    P_reduced = P / ref.P_crit
    if P_reduced > 0.99:
        P_reduced = 0.99
    h_tp = h_lo * ((1 - x)**0.8
                    + 3.8 * x**0.76 * (1 - x)**0.04
                    / max(P_reduced, 0.01)**0.38)

    return max(h_tp, 100.0)  # minimum 100 W/(m²·K)


def estimate_htc_air_side_louvered(V_air, geom):
    """Estimate air-side HTC for louvered fins.

    Simplified Wang et al. (1999) correlation.
    Returns h_air [W/(m²·K)]
    """
    # Approximate air properties at 35°C
    rho_air = 1.15   # kg/m³
    mu_air = 1.85e-5  # Pa·s
    k_air = 0.026     # W/(m·K)
    Pr_air = 0.71

    # Frontal velocity → maximum velocity
    sigma_ratio = 0.5  # approximate free-flow to frontal ratio
    V_max = V_air / sigma_ratio

    # Louver pitch ≈ fin pitch (approximate)
    Lp = 1.0 / geom.fin_density if geom.fin_density > 0 else 0.002

    # Reynolds number based on louver pitch
    Re_Lp = rho_air * V_max * Lp / mu_air

    # Colburn j-factor (simplified Wang et al. 1999)
    j = 0.249 * Re_Lp**(-0.42)  # approximate for typical louvered fin MCHX

    # h = j × G × cp / Pr^(2/3)
    G_air = rho_air * V_max
    cp_air = 1006.0
    h_air = j * G_air * cp_air / Pr_air**(2.0/3.0)

    return max(h_air, 10.0)


def solve_mchx_condenser(
    T_ref_in, P_cond, m_dot_ref,
    T_air_in, V_air_frontal,
    geom,
    ref,
    n_segments=30,
    htc_air_multiplier=1.22,    # HPDM HTADJ_AIR_D
    htc_ref_multiplier=0.94,    # HPDM HTADJ_REF
):
    """Solve microchannel condenser.

    Parameters
    ----------
    T_ref_in : float — inlet superheat refrigerant temperature [K]
    P_cond : float — condensing pressure [Pa]
    m_dot_ref : float — refrigerant mass flow rate [kg/s]
    T_air_in : float — outdoor air temperature [K]
    V_air_frontal : float — frontal air velocity [m/s]
    geom : MicrochannelGeometry
    ref : Refrigerant
    n_segments : int

    Returns
    -------
    CondenserResult
    """
    # Air mass flow rate
    rho_air = 1.15  # kg/m³ approximate
    m_dot_air = rho_air * V_air_frontal * geom.face_area

    # Estimate HTCs
    h_air = estimate_htc_air_side_louvered(V_air_frontal, geom) * htc_air_multiplier

    # Refrigerant mass flux per circuit
    G_ref = m_dot_ref / geom.A_cs_circuit if geom.A_cs_circuit > 0 else 100.0

    # Single-phase HTC (Dittus-Boelter)
    # Evaluate properties at a safely superheated state to avoid pseudo-pure issues
    T_sat = ref.T_sat(P_cond)
    T_prop = max(T_ref_in, T_sat + 5.0)  # ensure superheated for property eval
    try:
        mu_ref = ref.mu(T_prop, P_cond)
        k_ref = ref.k_thermal(T_prop, P_cond)
        cp_ref = ref.cp(T_prop, P_cond)
    except ValueError:
        # Fallback: use approximate R410A vapor properties
        mu_ref = 1.5e-5   # Pa·s
        k_ref = 0.015      # W/(m·K)
        cp_ref = 1200.0    # J/(kg·K)
    Pr_ref = mu_ref * cp_ref / k_ref
    Re_ref = G_ref * geom.D_h_port / mu_ref
    h_ref_sp = 0.023 * Re_ref**0.8 * Pr_ref**0.4 * k_ref / geom.D_h_port
    h_ref_sp = max(h_ref_sp, 100.0) * htc_ref_multiplier

    # Two-phase HTC (average at quality 0.5)
    h_ref_tp = estimate_htc_microchannel_condensation(G_ref, 0.5, geom.D_h_port, P_cond, ref) * htc_ref_multiplier

    # Solve one circuit, then scale charge by n_circuits.
    # Mass flow per circuit = total / n_circuits.
    # Air-side area per circuit = total / n_circuits (each circuit sees a portion).
    # Ref-side area per circuit = total / n_circuits.
    m_dot_per_circuit = m_dot_ref / geom.n_circuits
    m_dot_air_per_circuit = m_dot_air / geom.n_circuits
    A_air_per_circuit = geom.A_air_total / geom.n_circuits
    A_ref_per_circuit = geom.A_ref_total / geom.n_circuits

    result = solve_condenser(
        T_ref_in, P_cond, m_dot_per_circuit,
        T_air_in, m_dot_air_per_circuit,
        n_segments,
        geom.L_ref_circuit,
        A_air_per_circuit,
        A_ref_per_circuit,
        geom.A_cs_circuit,
        h_air, h_ref_sp, h_ref_tp,
        ref,
    )

    # Scale to total system (all circuits identical)
    result.Q_total *= geom.n_circuits
    result.charge_total *= geom.n_circuits

    # Add header volume charge if specified.
    # Headers contain a mix of subcooled liquid and two-phase refrigerant.
    # Approximate: 50% liquid density, 50% two-phase at average quality.
    V_header = getattr(geom, 'V_header_m3', 0.0)
    if V_header > 0:
        rho_l = ref.rho_sat_liquid(P_cond)
        rho_g = ref.rho_sat_vapor(P_cond)
        # Assume headers are ~60% liquid-filled (inlet header has two-phase,
        # outlet header has subcooled liquid)
        rho_header_avg = 0.6 * rho_l + 0.4 * (0.5 * rho_l + 0.5 * rho_g)
        charge_header = rho_header_avg * V_header
        result.charge_total += charge_header

    return result
