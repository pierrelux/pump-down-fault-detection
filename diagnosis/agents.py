"""
Diagnostic agents for the HVAC fault diagnosis environment.

Each agent is a function: (env, spec_sheet) -> Diagnosis
"""

from .environment import HVACEnvironment
from .evaluate import Diagnosis


def rule_based_agent(env: HVACEnvironment, spec_sheet: str) -> Diagnosis:
    """Baseline-comparison rule-based diagnosis.

    Takes one set of readings at normal fan speed and compares to baseline.
    """
    r = env.read_sensors(fan_speed=0.45)
    b = env.baseline

    d_sc = r.subcooling_F - b.subcooling_F
    d_sh = r.superheat_F - b.superheat_F
    d_psuc = r.suction_pressure_psi - b.suction_pressure_psi
    d_pdis = r.discharge_pressure_psi - b.discharge_pressure_psi

    # TXV faults: superheat changes significantly
    if d_sh < -4.0:
        return Diagnosis(fault_type="txv_stuck_open", confidence=0.9,
                         reasoning=f"SH dropped {d_sh:+.1f}°F from baseline ({b.superheat_F:.0f}→{r.superheat_F:.0f}°F).")
    if d_sh > 6.0:
        return Diagnosis(fault_type="txv_stuck_closed", confidence=0.9,
                         reasoning=f"SH rose {d_sh:+.1f}°F from baseline ({b.superheat_F:.0f}→{r.superheat_F:.0f}°F).")

    # Evaporator fouling: suction pressure drops
    if d_psuc < -10.0:
        return Diagnosis(fault_type="evap_fouling", confidence=0.8,
                         reasoning=f"P_suc dropped {d_psuc:+.1f} psi from baseline.")

    # Charge faults: subcooling changes
    if d_sc < -5.0:
        return Diagnosis(fault_type="low_charge", confidence=0.8,
                         reasoning=f"SC dropped {d_sc:+.1f}°F from baseline ({b.subcooling_F:.0f}→{r.subcooling_F:.0f}°F).")
    if d_sc > 10.0:
        return Diagnosis(fault_type="high_charge", confidence=0.7,
                         reasoning=f"SC rose {d_sc:+.1f}°F from baseline ({b.subcooling_F:.0f}→{r.subcooling_F:.0f}°F).")

    # Compressor wear: discharge pressure drops with moderate SC drop
    if d_pdis < -15.0 and d_sc < -2.0:
        return Diagnosis(fault_type="compressor_wear", confidence=0.6,
                         reasoning=f"P_dis dropped {d_pdis:+.1f} psi and SC dropped {d_sc:+.1f}°F from baseline.")

    return Diagnosis(fault_type="healthy", confidence=0.7,
                     reasoning=f"Readings close to baseline: dSC={d_sc:+.1f}°F, dSH={d_sh:+.1f}°F, "
                               f"dP_suc={d_psuc:+.1f}, dP_dis={d_pdis:+.1f}.")


def active_rule_agent(env: HVACEnvironment, spec_sheet: str) -> Diagnosis:
    """Baseline-comparison agent with fan speed perturbation.

    Compares current readings to baseline, then uses fan speed test
    to disambiguate charge vs compressor faults.
    """
    r = env.read_sensors(fan_speed=0.45)
    b = env.baseline

    d_sc = r.subcooling_F - b.subcooling_F
    d_sh = r.superheat_F - b.superheat_F
    d_psuc = r.suction_pressure_psi - b.suction_pressure_psi
    d_pdis = r.discharge_pressure_psi - b.discharge_pressure_psi

    # TXV faults
    if d_sh < -4.0:
        return Diagnosis(fault_type="txv_stuck_open", confidence=0.9,
                         reasoning=f"SH dropped {d_sh:+.1f}°F from baseline.")
    if d_sh > 6.0:
        return Diagnosis(fault_type="txv_stuck_closed", confidence=0.9,
                         reasoning=f"SH rose {d_sh:+.1f}°F from baseline.")

    # Evaporator fouling
    if d_psuc < -10.0:
        return Diagnosis(fault_type="evap_fouling", confidence=0.8,
                         reasoning=f"P_suc dropped {d_psuc:+.1f} psi from baseline.")

    # Something is off with SC or P_dis — do fan test to disambiguate
    if d_sc < -3.0 or d_pdis < -10.0:
        r_high = env.read_sensors(fan_speed=0.80)
        sc_response = r_high.subcooling_F - r.subcooling_F

        if r.subcooling_F < 3.0:
            return Diagnosis(fault_type="low_charge", confidence=0.9,
                             reasoning=f"SC={r.subcooling_F:.1f}°F (baseline {b.subcooling_F:.0f}°F), "
                                       f"fan test SC delta={sc_response:+.1f}°F. No liquid to subcool.")

        # Both low charge and compressor wear drop SC and P_dis.
        # Compressor wear also drops mdot, which we can't measure directly,
        # but the fan test response differs.
        return Diagnosis(fault_type="compressor_wear", confidence=0.6,
                         reasoning=f"SC dropped {d_sc:+.1f}°F, P_dis dropped {d_pdis:+.1f} psi, "
                                   f"fan test SC delta={sc_response:+.1f}°F.")

    if d_sc > 10.0:
        return Diagnosis(fault_type="high_charge", confidence=0.7,
                         reasoning=f"SC rose {d_sc:+.1f}°F from baseline.")

    return Diagnosis(fault_type="healthy", confidence=0.7,
                     reasoning=f"Readings close to baseline: dSC={d_sc:+.1f}°F, dP_dis={d_pdis:+.1f}.")
