"""
Charge inventory calculation.

Computes the total refrigerant charge in each component of the system:
- Condenser (from segment-by-segment model)
- Evaporator (from segment-by-segment model)
- Liquid line
- Suction line
- Discharge line
- Compressor shell

For the pump-down charge prediction method, only the condenser charge at
steady-state (before pump-down) is needed from the HX model. The remaining
charge is determined from the pump-down integration.

Reference: ORNL/CON-343, Section on Charge Inventory.
"""
import numpy as np
from ..properties.refrigerant import Refrigerant


def charge_in_line(length, D_inner, rho):
    """Refrigerant mass in a connecting line [kg].

    M = ρ × A_cs × L

    Parameters
    ----------
    length : float — pipe length [m]
    D_inner : float — inner diameter [m]
    rho : float — refrigerant density [kg/m³] (liquid, vapor, or two-phase)

    Returns
    -------
    M : float — refrigerant mass [kg]
    """
    A_cs = np.pi / 4.0 * D_inner**2
    return rho * A_cs * length


def charge_in_liquid_line(length, D_inner, P, T_subcooled, ref):
    """Charge in liquid line [kg].

    Liquid line contains subcooled liquid refrigerant.
    """
    rho = ref.rho(T_subcooled, P)
    return charge_in_line(length, D_inner, rho)


def charge_in_suction_line(length, D_inner, P, T_superheat, ref):
    """Charge in suction line [kg].

    Suction line contains superheated vapor.
    """
    rho = ref.rho(T_superheat, P)
    return charge_in_line(length, D_inner, rho)


def charge_in_discharge_line(length, D_inner, P, T_discharge, ref):
    """Charge in discharge line [kg].

    Discharge line contains superheated vapor at high pressure.
    """
    rho = ref.rho(T_discharge, P)
    return charge_in_line(length, D_inner, rho)


def charge_in_compressor_shell(V_shell, P_suction, T_suction, ref,
                                oil_fraction=0.05):
    """Approximate charge in compressor shell [kg].

    Compressor shell contains superheated vapor + dissolved refrigerant in oil.

    Parameters
    ----------
    V_shell : float — shell internal volume [m³]
    P_suction : float — suction pressure [Pa]
    T_suction : float — suction temperature [K]
    ref : Refrigerant
    oil_fraction : float — fraction of shell volume occupied by oil

    Returns
    -------
    M : float — refrigerant mass [kg]
    """
    V_vapor = V_shell * (1.0 - oil_fraction)
    rho_vapor = ref.rho(T_suction, P_suction)
    return rho_vapor * V_vapor


class SystemChargeInventory:
    """Total system charge broken down by component."""

    def __init__(self):
        self.condenser = 0.0       # kg
        self.evaporator = 0.0      # kg
        self.liquid_line = 0.0     # kg
        self.suction_line = 0.0    # kg
        self.discharge_line = 0.0  # kg
        self.compressor = 0.0      # kg
        self.accumulator = 0.0     # kg
        self.total = 0.0           # kg

    def compute_total(self):
        self.total = (self.condenser + self.evaporator + self.liquid_line
                      + self.suction_line + self.discharge_line
                      + self.compressor + self.accumulator)
        return self.total

    def __repr__(self):
        return (
            f"SystemChargeInventory(\n"
            f"  condenser  = {self.condenser:.4f} kg\n"
            f"  evaporator = {self.evaporator:.4f} kg\n"
            f"  liquid_line = {self.liquid_line:.4f} kg\n"
            f"  suction_line = {self.suction_line:.4f} kg\n"
            f"  discharge_line = {self.discharge_line:.4f} kg\n"
            f"  compressor = {self.compressor:.4f} kg\n"
            f"  accumulator = {self.accumulator:.4f} kg\n"
            f"  TOTAL = {self.total:.4f} kg\n"
            f")"
        )
