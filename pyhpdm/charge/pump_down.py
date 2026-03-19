"""
Pump-down charge prediction simulator.

Implements the charge prediction method from Li, Shen, Welch & Gluesenkamp (2024).

During pump-down:
1. The liquid line valve closes
2. The compressor runs, migrating refrigerant from LP (evaporator) to HP (condenser)
3. The 4-way valve leaks some refrigerant back from HP to LP
4. Suction pressure drops; discharge pressure rises slightly then stabilizes
5. Pump-down terminates when low-pressure protection activates (~20 psi for R410A)

LP-side physics:
  - Initially, the evaporator contains two-phase refrigerant (liquid + vapor)
  - Phase 1 (liquid present): as compressor removes vapor, liquid boils to replace it.
    Pressure stays approximately at P_sat(T_evap). Liquid mass decreases.
  - Phase 2 (vapor only): once all liquid has boiled off, pressure drops rapidly
    as the remaining superheated vapor is evacuated from the LP volume.

=== Eq. (1): Total charge decomposition ===
Charge = Charge_viaCompressor - Charge_viaFourWayValve
         + CondenserCharge_BeforePumpDown + LowPressureSideCharge_AfterPumpDown

DEVIATION DEV-004: We simulate the pressure traces rather than using
experimental measurements. See DEVIATIONS.md.
"""
import numpy as np
import CoolProp.CoolProp as CP
from ..properties.refrigerant import Refrigerant, F_to_K, K_to_F, psi_to_Pa, Pa_to_psi
from ..components.compressor import CompressorMap, mass_flow_during_pumpdown
from ..components.valve import four_way_valve_leakage


class PumpDownState:
    """State of the system at one timestep during pump-down."""
    def __init__(self):
        self.time = 0.0
        self.P_suction = 0.0            # Pa
        self.P_discharge = 0.0          # Pa
        self.T_suction = 0.0            # K
        self.T_discharge = 0.0          # K
        self.m_dot_compressor = 0.0     # kg/s
        self.m_dot_valve = 0.0          # kg/s
        self.eta_vol = 0.0
        self.charge_migrated_cum = 0.0  # kg
        self.charge_leaked_cum = 0.0    # kg
        self.M_LP = 0.0                 # kg remaining in LP
        self.M_LP_liquid = 0.0          # kg liquid in LP
        self.phase = ""                 # "two_phase" or "vapor_only"


class PumpDownResult:
    """Results from a pump-down simulation."""
    def __init__(self):
        self.states = []
        self.duration = 0.0
        self.charge_migrated_total = 0.0
        self.charge_leaked_total = 0.0
        self.condenser_charge_static = 0.0
        self.total_charge_predicted = 0.0
        self.terminated_by = ""


def simulate_pump_down(
    compressor,
    Cv_valve,
    P_suction_initial_Pa,
    P_discharge_initial_Pa,
    T_outdoor_K,
    V_LP_m3,
    ref,
    M_LP_initial_kg=None,
    P_low_cutoff_Pa=None,
    dt=0.5,
    max_time=200.0,
    T_superheat_initial_K=5.0,
    x_initial=0.2,
):
    """Simulate the pump-down transient process.

    The LP side is modeled as a constant-volume two-phase reservoir.
    Phase 1: While liquid is present, P ≈ P_sat(T_evap), liquid boils off.
    Phase 2: Once all liquid has boiled, P drops as superheated vapor evacuates.

    Parameters
    ----------
    compressor : CompressorMap
    Cv_valve : float — 4-way valve leakage coefficient [m³/(s·Pa²)]
    P_suction_initial_Pa : float — initial suction pressure [Pa]
    P_discharge_initial_Pa : float — initial discharge pressure [Pa]
    T_outdoor_K : float — outdoor ambient temperature [K]
    V_LP_m3 : float — total LP-side volume [m³]
    ref : Refrigerant
    M_LP_initial_kg : float or None — initial LP mass [kg]. If None, computed from
        two-phase state at (P_suction, x_initial).
    P_low_cutoff_Pa : float — low-pressure cutoff [Pa] (default: 20 psi)
    dt : float — timestep [s]
    max_time : float — maximum simulation time [s]
    T_superheat_initial_K : float — initial suction superheat [K]
    x_initial : float — initial average quality in LP side

    Returns
    -------
    PumpDownResult
    """
    if P_low_cutoff_Pa is None:
        P_low_cutoff_Pa = psi_to_Pa(20.0)

    result = PumpDownResult()

    P_suc = P_suction_initial_Pa
    P_dis = P_discharge_initial_Pa

    # Initial LP state: two-phase refrigerant at evaporating conditions
    rho_l = ref.rho_sat_liquid(P_suc)
    rho_g = ref.rho_sat_vapor(P_suc)

    if M_LP_initial_kg is not None:
        M_LP = M_LP_initial_kg
    else:
        # Compute initial LP mass from volume and quality
        # V = M_liquid/rho_l + M_vapor/rho_g
        # M = M_liquid + M_vapor, x = M_vapor/M
        # V = M × [(1-x)/rho_l + x/rho_g]
        v_avg = (1.0 - x_initial) / rho_l + x_initial / rho_g
        M_LP = V_LP_m3 / v_avg

    # Compute initial liquid and vapor masses
    # V_LP = M_liq/rho_l + M_vap/rho_g and M_LP = M_liq + M_vap
    # x = M_vap / M_LP → M_vap = x * M_LP, M_liq = (1-x) * M_LP
    M_LP_liquid = (1.0 - x_initial) * M_LP
    M_LP_vapor = x_initial * M_LP

    T_evap = ref.T_sat(P_suc)
    T_suc = T_evap + T_superheat_initial_K

    charge_migrated = 0.0
    charge_leaked = 0.0
    t = 0.0
    in_two_phase = M_LP_liquid > 0.001

    while t < max_time:
        if P_suc <= P_low_cutoff_Pa:
            result.terminated_by = "low_pressure"
            break

        if M_LP <= 1e-6:
            result.terminated_by = "empty_LP"
            break

        # Suction temperature
        if in_two_phase:
            T_suc = T_evap + 2.0  # slight superheat at compressor inlet
        else:
            # Vapor only — temperature rises toward ambient
            T_suc = min(T_evap + 20.0, T_outdoor_K)

        # Discharge temperature
        T_sat_dis = ref.T_sat(P_dis)
        T_dis = T_sat_dis + 15.0

        # Compressor mass flow (Eq. 4)
        m_dot_comp, eta_vol = mass_flow_during_pumpdown(
            compressor, P_suc, P_dis, T_suc
        )
        m_dot_comp = max(m_dot_comp, 0.0)

        # 4-way valve leakage (Eq. 5-6)
        m_dot_valve_leak, _ = four_way_valve_leakage(
            P_dis, P_suc, T_dis, Cv_valve, ref
        )

        # Net mass removal from LP side
        m_dot_net = m_dot_comp - m_dot_valve_leak
        m_dot_net = max(m_dot_net, 0.0)

        # Record state
        state = PumpDownState()
        state.time = t
        state.P_suction = P_suc
        state.P_discharge = P_dis
        state.T_suction = T_suc
        state.T_discharge = T_dis
        state.m_dot_compressor = m_dot_comp
        state.m_dot_valve = m_dot_valve_leak
        state.eta_vol = eta_vol
        state.charge_migrated_cum = charge_migrated
        state.charge_leaked_cum = charge_leaked
        state.M_LP = M_LP
        state.M_LP_liquid = M_LP_liquid
        state.phase = "two_phase" if in_two_phase else "vapor_only"
        result.states.append(state)

        # Update mass
        dM = m_dot_net * dt
        charge_migrated += m_dot_comp * dt
        charge_leaked += m_dot_valve_leak * dt

        if in_two_phase:
            # Phase 1: liquid present.
            # Compressor removes superheated vapor from suction line.
            # Liquid in evaporator boils to replace it. Pressure stays at P_sat(T_evap).
            # Net effect: liquid mass decreases.
            M_LP_liquid -= dM
            M_LP -= dM

            if M_LP_liquid <= 0.0:
                # Transition to vapor-only phase
                M_LP_liquid = 0.0
                in_two_phase = False
                M_LP = max(M_LP, 0.0)
                # Recompute: remaining mass is all vapor in V_LP
                # M_LP = rho_g(P_suc) × V_LP at the transition point
        else:
            # Phase 2: vapor only.
            # Compressor removes superheated vapor. Pressure drops.
            M_LP -= dM
            M_LP = max(M_LP, 0.0)

            # Update P from density and temperature using CoolProp EOS
            rho_LP_new = M_LP / V_LP_m3
            if rho_LP_new > 0.1:
                try:
                    P_suc = CP.PropsSI("P", "D", rho_LP_new, "T", T_suc, ref.fluid)
                except (ValueError, RuntimeError):
                    # Fallback: scale pressure proportionally to density
                    P_suc = P_suc * (rho_LP_new / (M_LP + dM) * V_LP_m3)
            else:
                P_suc = P_low_cutoff_Pa * 0.5

            # Update T_evap for next iteration
            if P_suc > P_low_cutoff_Pa * 0.5:
                try:
                    T_evap = ref.T_sat(P_suc)
                except ValueError:
                    pass

        # Discharge pressure: condenser fan running, relatively stable
        T_cond_approach = 10.0 + 5.0 * (charge_migrated / max(M_LP + charge_migrated, 0.1))
        T_cond_approach = min(T_cond_approach, 20.0)
        try:
            P_dis = ref.P_sat(T_outdoor_K + T_cond_approach)
        except ValueError:
            pass

        t += dt

    if not result.terminated_by:
        result.terminated_by = "max_time"

    result.duration = t
    result.charge_migrated_total = charge_migrated
    result.charge_leaked_total = charge_leaked

    return result


def predict_total_charge(condenser_charge_static_kg, pump_down_result):
    """Calculate total system charge from pump-down results.

    === Eq. (1) of Li & Shen (2024) ===
    Charge = Charge_viaCompressor - Charge_viaFourWayValve
             + CondenserCharge_BeforePumpDown

    The LowPressureSideCharge_AfterPumpDown term is neglected.
    """
    total = (condenser_charge_static_kg
             + pump_down_result.charge_migrated_total
             - pump_down_result.charge_leaked_total)

    pump_down_result.condenser_charge_static = condenser_charge_static_kg
    pump_down_result.total_charge_predicted = total

    return total
