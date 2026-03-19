"""
Diagnostic agents for the HVAC fault diagnosis environment.

Each agent is a function: (env, spec_sheet) -> Diagnosis
"""

from .environment import HVACEnvironment
from .evaluate import Diagnosis


def rule_based_agent(env: HVACEnvironment, spec_sheet: str) -> Diagnosis:
    """ASHRAE-style single-reading rule-based diagnosis.

    Takes one set of readings at normal fan speed and applies fixed rules.
    No active testing.
    """
    r = env.read_sensors(fan_speed=0.45)

    # TXV faults: superheat is the giveaway
    if r.superheat_F < 4.0:
        return Diagnosis(
            fault_type="txv_stuck_open",
            confidence=0.9,
            reasoning=f"Superheat is {r.superheat_F:.1f}°F, well below normal 8-14°F range. "
                      "TXV is likely stuck open, allowing liquid flood-back.",
        )
    if r.superheat_F > 16.0:
        return Diagnosis(
            fault_type="txv_stuck_closed",
            confidence=0.9,
            reasoning=f"Superheat is {r.superheat_F:.1f}°F, above normal 8-14°F range. "
                      "TXV is likely stuck closed or restricted.",
        )

    # Low suction pressure: evaporator fouling
    if r.suction_pressure_psi < 160.0:
        return Diagnosis(
            fault_type="evap_fouling",
            confidence=0.7,
            reasoning=f"Suction pressure is {r.suction_pressure_psi:.1f} psi, below normal "
                      "120-180 range. Low suction pressure with normal superheat suggests "
                      "reduced airflow across evaporator (fouling or blower issue).",
        )

    # Subcooling-based charge diagnosis
    if r.subcooling_F < 3.0:
        return Diagnosis(
            fault_type="low_charge",
            confidence=0.8,
            reasoning=f"Subcooling is {r.subcooling_F:.1f}°F, well below normal 8-18°F. "
                      "Very low subcooling indicates insufficient refrigerant charge.",
        )

    if r.subcooling_F > 22.0:
        return Diagnosis(
            fault_type="high_charge",
            confidence=0.7,
            reasoning=f"Subcooling is {r.subcooling_F:.1f}°F, above normal 8-18°F. "
                      "High subcooling suggests system is overcharged.",
        )

    # Low discharge pressure + moderate subcooling: compressor wear
    if r.discharge_pressure_psi < 350.0 and r.subcooling_F < 12.0:
        return Diagnosis(
            fault_type="compressor_wear",
            confidence=0.5,
            reasoning=f"Discharge pressure is {r.discharge_pressure_psi:.1f} psi (low) "
                      f"with subcooling {r.subcooling_F:.1f}°F (moderate). Suggests reduced "
                      "compressor capacity.",
        )

    return Diagnosis(
        fault_type="healthy",
        confidence=0.6,
        reasoning=f"Readings within normal ranges: P_suc={r.suction_pressure_psi:.0f}, "
                  f"P_dis={r.discharge_pressure_psi:.0f}, SC={r.subcooling_F:.1f}°F, "
                  f"SH={r.superheat_F:.1f}°F.",
    )


def active_rule_agent(env: HVACEnvironment, spec_sheet: str) -> Diagnosis:
    """Rule-based agent that uses fan speed perturbation to disambiguate.

    Takes a baseline reading, then bumps the fan to high speed and checks
    whether subcooling responds.
    """
    r_normal = env.read_sensors(fan_speed=0.45)

    # TXV faults (no fan test needed)
    if r_normal.superheat_F < 4.0:
        return Diagnosis(fault_type="txv_stuck_open", confidence=0.9,
                         reasoning=f"SH={r_normal.superheat_F:.1f}°F is very low.")
    if r_normal.superheat_F > 16.0:
        return Diagnosis(fault_type="txv_stuck_closed", confidence=0.9,
                         reasoning=f"SH={r_normal.superheat_F:.1f}°F is very high.")

    # Low suction pressure: evaporator fouling
    if r_normal.suction_pressure_psi < 160.0:
        return Diagnosis(fault_type="evap_fouling", confidence=0.8,
                         reasoning=f"P_suc={r_normal.suction_pressure_psi:.1f} psi is low "
                                   "with normal SH — evaporator airflow issue.")

    # Fan speed test for charge/compressor disambiguation
    if r_normal.subcooling_F < 12.0 or r_normal.discharge_pressure_psi < 365.0:
        r_high_fan = env.read_sensors(fan_speed=0.80)
        sc_delta = r_high_fan.subcooling_F - r_normal.subcooling_F

        if r_normal.subcooling_F < 3.0:
            # Very low SC, doesn't respond to fan → low charge
            return Diagnosis(fault_type="low_charge", confidence=0.9,
                             reasoning=f"SC={r_normal.subcooling_F:.1f}°F near zero, "
                                       f"fan test delta={sc_delta:.1f}°F confirms low charge.")
        else:
            # Moderate SC drop + low P_dis → compressor wear
            return Diagnosis(fault_type="compressor_wear", confidence=0.7,
                             reasoning=f"SC={r_normal.subcooling_F:.1f}°F moderate, "
                                       f"P_dis={r_normal.discharge_pressure_psi:.0f} low, "
                                       f"fan test SC delta={sc_delta:.1f}°F.")

    if r_normal.subcooling_F > 22.0:
        return Diagnosis(fault_type="high_charge", confidence=0.7,
                         reasoning=f"SC={r_normal.subcooling_F:.1f}°F is high — overcharged.")

    return Diagnosis(fault_type="healthy", confidence=0.6,
                     reasoning="All readings within normal ranges.")
