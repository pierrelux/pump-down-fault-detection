"""
Diagnostic agents for the HVAC fault diagnosis environment.

Each agent is a function: (env, spec_sheet) -> Diagnosis
"""

from .environment import HVACEnvironment
from .evaluate import Diagnosis


def anomaly_detector(env: HVACEnvironment, spec_sheet: str) -> Diagnosis:
    """Naive anomaly detector — no fault classification.

    Flags as faulty if any reading deviates more than 10% from baseline.
    If faulty, guesses the most common fault type (low_charge) since it
    can't distinguish. This is the "detection without diagnosis" baseline.
    """
    r = env.read_sensors(fan_speed=0.45)
    b = env.baseline

    # Check percent deviation on each measurable
    deviations = {}
    for name, cur, base in [
        ("P_suc", r.suction_pressure_psi, b.suction_pressure_psi),
        ("P_dis", r.discharge_pressure_psi, b.discharge_pressure_psi),
        ("SC", r.subcooling_F, b.subcooling_F),
        ("SH", r.superheat_F, b.superheat_F),
        ("T_dis", r.discharge_temperature_F, b.discharge_temperature_F),
    ]:
        if abs(base) > 1.0:
            deviations[name] = (cur - base) / base * 100
        else:
            # For values near zero (e.g. SC=0), use absolute difference
            deviations[name] = cur - base

    # Flag if any reading deviates > 10%
    is_faulty = any(abs(d) > 10.0 for d in deviations.values())

    dev_str = ", ".join(f"{k}={v:+.1f}%" for k, v in deviations.items())

    if is_faulty:
        # Can detect something is wrong but can't say what
        return Diagnosis(
            fault_type="low_charge",  # blind guess — most common fault
            confidence=0.3,
            reasoning=f"Anomaly detected (>{10}% deviation from baseline): {dev_str}. "
                      "Cannot determine fault type — guessing low_charge.",
        )

    return Diagnosis(
        fault_type="healthy",
        confidence=0.5,
        reasoning=f"All readings within 10% of baseline: {dev_str}.",
    )


def random_agent(env: HVACEnvironment, spec_sheet: str) -> Diagnosis:
    """Random baseline — takes no readings, guesses uniformly."""
    import random
    from .environment import FAULT_TYPES
    return Diagnosis(
        fault_type=random.choice(FAULT_TYPES),
        confidence=0.14,
        reasoning="Random guess.",
    )
