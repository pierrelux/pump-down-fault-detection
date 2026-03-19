"""
HVAC fault diagnosis environment.

Wraps the pyhpdm charge-balance solver as a tool-callable interface.
The agent sees sensor readings but not the underlying fault parameters.
"""

import random
import warnings
from dataclasses import dataclass, field
from typing import Optional

from pyhpdm.properties.refrigerant import (
    Refrigerant, F_to_K, K_to_F, Pa_to_psi, LBM_TO_KG,
)
from pyhpdm.components.compressor import CompressorMap
from pyhpdm.components.heat_exchanger.microchannel import OUTDOOR_MCHX_SPLIT
from pyhpdm.solver.system import solve_charge_balance, SystemGeometry


# ============================================================================
# Fault definition
# ============================================================================

FAULT_TYPES = ["healthy", "low_charge", "high_charge",
               "evap_fouling", "compressor_wear", "txv_stuck_open", "txv_stuck_closed"]


@dataclass
class FaultScenario:
    """A hidden fault injected into the system."""
    fault_type: str = "healthy"

    # Charge
    charge_lbm: float = 8.08           # nominal = 8.08

    # Evaporator fouling: extra approach [K] (0 = healthy)
    evap_fouling_K: float = 0.0

    # Compressor degradation: multiplier (1.0 = healthy)
    compressor_degradation: float = 1.0

    # TXV superheat override [K] (5.0 = healthy)
    superheat_K: float = 5.0

    # Operating condition
    T_outdoor_F: float = 95.0
    T_indoor_F: float = 80.0

    def description(self):
        """Human-readable description of the injected fault."""
        if self.fault_type == "healthy":
            return f"Healthy system, {self.charge_lbm:.2f} lbm, {self.T_outdoor_F:.0f}°F outdoor"
        elif self.fault_type == "low_charge":
            pct = (1 - self.charge_lbm / 8.08) * 100
            return f"Low charge: {self.charge_lbm:.2f} lbm ({pct:.0f}% under)"
        elif self.fault_type == "high_charge":
            pct = (self.charge_lbm / 8.08 - 1) * 100
            return f"High charge: {self.charge_lbm:.2f} lbm ({pct:.0f}% over)"
        elif self.fault_type == "evap_fouling":
            return f"Evaporator fouling: +{self.evap_fouling_K:.1f} K approach"
        elif self.fault_type == "compressor_wear":
            pct = (1 - self.compressor_degradation) * 100
            return f"Compressor wear: {pct:.0f}% degraded"
        elif self.fault_type == "txv_stuck_open":
            return f"TXV stuck open: superheat = {self.superheat_K * 9/5:.0f}°F"
        elif self.fault_type == "txv_stuck_closed":
            return f"TXV stuck closed: superheat = {self.superheat_K * 9/5:.0f}°F"
        return self.fault_type


def random_fault(rng=None):
    """Sample a random fault scenario."""
    if rng is None:
        rng = random.Random()

    T_outdoor_F = rng.choice([75.0, 82.0, 90.0, 95.0, 100.0])
    fault_type = rng.choice(FAULT_TYPES)

    scenario = FaultScenario(
        fault_type=fault_type,
        T_outdoor_F=T_outdoor_F,
    )

    if fault_type == "healthy":
        pass
    elif fault_type == "low_charge":
        scenario.charge_lbm = rng.uniform(5.5, 7.5)
    elif fault_type == "high_charge":
        scenario.charge_lbm = rng.uniform(8.5, 9.5)
    elif fault_type == "evap_fouling":
        scenario.evap_fouling_K = rng.uniform(3.0, 12.0)
    elif fault_type == "compressor_wear":
        scenario.compressor_degradation = rng.uniform(0.65, 0.92)
    elif fault_type == "txv_stuck_open":
        scenario.superheat_K = rng.uniform(0.3, 1.5)
    elif fault_type == "txv_stuck_closed":
        scenario.superheat_K = rng.uniform(8.0, 15.0)

    return scenario


# ============================================================================
# Sensor readings
# ============================================================================

@dataclass
class SensorReadings:
    """What a technician measures with gauges and thermocouples."""
    suction_pressure_psi: float
    discharge_pressure_psi: float
    suction_temperature_F: float
    liquid_line_temperature_F: float
    discharge_temperature_F: float
    outdoor_temperature_F: float
    indoor_temperature_F: float

    # Derived (technician computes from gauge + thermocouple)
    superheat_F: float
    subcooling_F: float

    # Not directly measured but included for evaluation
    _mass_flow_lbm_h: float = 0.0

    def to_dict(self):
        return {
            "suction_pressure_psi": round(self.suction_pressure_psi, 1),
            "discharge_pressure_psi": round(self.discharge_pressure_psi, 1),
            "suction_temperature_F": round(self.suction_temperature_F, 1),
            "liquid_line_temperature_F": round(self.liquid_line_temperature_F, 1),
            "discharge_temperature_F": round(self.discharge_temperature_F, 1),
            "outdoor_temperature_F": round(self.outdoor_temperature_F, 1),
            "indoor_temperature_F": round(self.indoor_temperature_F, 1),
            "superheat_F": round(self.superheat_F, 1),
            "subcooling_F": round(self.subcooling_F, 1),
        }

    def __str__(self):
        lines = [
            f"  Suction pressure:    {self.suction_pressure_psi:.1f} psi",
            f"  Discharge pressure:  {self.discharge_pressure_psi:.1f} psi",
            f"  Suction temperature: {self.suction_temperature_F:.1f}°F",
            f"  Liquid line temp:    {self.liquid_line_temperature_F:.1f}°F",
            f"  Discharge temp:      {self.discharge_temperature_F:.1f}°F",
            f"  Outdoor temp:        {self.outdoor_temperature_F:.1f}°F",
            f"  Indoor temp:         {self.indoor_temperature_F:.1f}°F",
            f"  Superheat:           {self.superheat_F:.1f}°F",
            f"  Subcooling:          {self.subcooling_F:.1f}°F",
        ]
        return "\n".join(lines)


# ============================================================================
# Environment
# ============================================================================

# System hardware (fixed — same compressor + geometry for all scenarios)
_COMPRESSOR_COEFFS_MDOT = [
    176.0, 2.72, -2.12, 0.0172, -0.0112, 0.0181,
    6.52e-5, 1.08e-5, 4.00e-5, -5.54e-5,
]
_COMPRESSOR_COEFFS_POWER = [
    1590.0, 6.79, -34.9, -0.226, -0.0660, 0.388,
    -1.37e-5, 1.01e-3, 7.41e-4, -1.12e-3,
]


class HVACEnvironment:
    """Simulated HVAC system that an agent can query.

    The agent interacts via:
        readings = env.read_sensors()              # default fan speed
        readings = env.read_sensors(fan_speed=0.8)  # high fan
        readings = env.read_sensors(fan_speed=0.2)  # low fan

    The environment hides the fault type and severity.
    """

    def __init__(self, scenario: FaultScenario):
        self.scenario = scenario
        self._query_count = 0

        self._ref = Refrigerant("R410A")
        self._compressor = CompressorMap(
            coeffs_mdot=_COMPRESSOR_COEFFS_MDOT,
            coeffs_power=_COMPRESSOR_COEFFS_POWER,
            V_displacement=0.000501302 * 0.0283168,
            N_rpm=3600.0,
            refrigerant="R410A",
            T_sh_rated_K=11.1,
            F_mass=0.75,
        )
        self._geom = SystemGeometry.paper_split_system()

        # Pre-compute baseline: what this unit looked like when healthy,
        # at the same outdoor temperature
        self._baseline = self._compute_readings(
            charge_lbm=8.08,
            superheat_K=5.0,
            evap_fouling_K=0.0,
            compressor_degradation=1.0,
            T_outdoor_F=scenario.T_outdoor_F,
            T_indoor_F=scenario.T_indoor_F,
            fan_speed=0.45,
        )

    @property
    def query_count(self):
        return self._query_count

    @property
    def baseline(self) -> SensorReadings:
        """Readings from last maintenance visit (system verified healthy).

        Same outdoor/indoor temperature as the current scenario.
        """
        return self._baseline

    def _compute_readings(self, charge_lbm, superheat_K, evap_fouling_K,
                          compressor_degradation, T_outdoor_F, T_indoor_F,
                          fan_speed) -> SensorReadings:
        """Compute sensor readings for given system state."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ss = solve_charge_balance(
                M_target_kg=charge_lbm * LBM_TO_KG,
                T_outdoor_K=F_to_K(T_outdoor_F),
                compressor=self._compressor,
                condenser_geom=OUTDOOR_MCHX_SPLIT,
                system_geom=self._geom,
                ref=self._ref,
                V_air_frontal=fan_speed,
                T_indoor_K=F_to_K(T_indoor_F),
                superheat_K=superheat_K,
                n_segments=30,
                evap_approach_K=12.0 + evap_fouling_K,
                compressor_degradation=compressor_degradation,
            )

        T_sat_suction_F = K_to_F(ss.T_evap_K)
        T_suction_F = T_sat_suction_F + ss.superheat_K * 9.0 / 5.0
        T_sat_discharge_F = K_to_F(ss.T_cond_K)
        T_liquid_line_F = T_sat_discharge_F - ss.subcooling_K * 9.0 / 5.0

        return SensorReadings(
            suction_pressure_psi=Pa_to_psi(ss.P_evap_Pa),
            discharge_pressure_psi=Pa_to_psi(ss.P_cond_Pa),
            suction_temperature_F=T_suction_F,
            liquid_line_temperature_F=T_liquid_line_F,
            discharge_temperature_F=K_to_F(ss.T_discharge_K),
            outdoor_temperature_F=T_outdoor_F,
            indoor_temperature_F=T_indoor_F,
            superheat_F=ss.superheat_K * 9.0 / 5.0,
            subcooling_F=ss.subcooling_K * 9.0 / 5.0,
            _mass_flow_lbm_h=ss.m_dot_kg_s / LBM_TO_KG * 3600,
        )

    def read_sensors(self, fan_speed: float = 0.45) -> SensorReadings:
        """Take sensor readings at given condenser fan speed [m/s].

        fan_speed: condenser air frontal velocity.
            0.45 = normal, 0.20 = low, 0.80 = high.
        """
        self._query_count += 1
        s = self.scenario
        return self._compute_readings(
            charge_lbm=s.charge_lbm,
            superheat_K=s.superheat_K,
            evap_fouling_K=s.evap_fouling_K,
            compressor_degradation=s.compressor_degradation,
            T_outdoor_F=s.T_outdoor_F,
            T_indoor_F=s.T_indoor_F,
            fan_speed=fan_speed,
        )
