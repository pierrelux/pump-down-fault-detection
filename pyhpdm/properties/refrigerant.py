"""
Refrigerant property wrapper using CoolProp.

Provides all thermodynamic properties needed for the charge prediction model:
density, enthalpy, entropy, saturation temperatures/pressures, surface tension,
viscosity, specific heats, thermal conductivity.

DEVIATION DEV-001: Uses CoolProp instead of REFPROP. See DEVIATIONS.md.

Reference: CoolProp documentation for R410A pseudo-pure fluid.
R410A is a near-azeotropic mixture (R32/R125, 50/50 wt%).
CoolProp treats it as pseudo-pure: use Q=0 for bubble, Q=1 for dew.
"""
import CoolProp.CoolProp as CP

# Supported refrigerants with CoolProp backend names
REFRIGERANTS = {
    "R410A": "R410A",
    "R22": "R22",
    "R134a": "R134a",
    "R32": "R32",
    "R407C": "R407C",
    "R404A": "R404A",
    "R290": "R290",       # propane
    "R600a": "R600a",     # isobutane
    "R744": "CO2",
}

# Unit conversion constants
LBM_TO_KG = 0.45359237
LBM_PER_H_TO_KG_PER_S = LBM_TO_KG / 3600.0
BTU_TO_J = 1055.06
PSI_TO_PA = 6894.757
F_TO_C_OFFSET = 32.0
IN3_TO_M3 = 1.6387064e-5


def F_to_K(T_F):
    """Convert Fahrenheit to Kelvin."""
    return (T_F - 32.0) * 5.0 / 9.0 + 273.15


def K_to_F(T_K):
    """Convert Kelvin to Fahrenheit."""
    return (T_K - 273.15) * 9.0 / 5.0 + 32.0


def psi_to_Pa(p_psi):
    """Convert psi to Pascals."""
    return p_psi * PSI_TO_PA


def Pa_to_psi(p_Pa):
    """Convert Pascals to psi."""
    return p_Pa / PSI_TO_PA


class Refrigerant:
    """Wrapper around CoolProp for a single refrigerant."""

    def __init__(self, name="R410A"):
        if name not in REFRIGERANTS:
            raise ValueError(f"Unknown refrigerant: {name}. Supported: {list(REFRIGERANTS)}")
        self.name = name
        self.fluid = REFRIGERANTS[name]

        # Cache critical point properties
        self.T_crit = CP.PropsSI("Tcrit", self.fluid)   # K
        self.P_crit = CP.PropsSI("pcrit", self.fluid)    # Pa
        self.M_molar = CP.PropsSI("M", self.fluid)       # kg/mol

    # --- Saturation properties ---

    def T_sat(self, P, Q=1):
        """Saturation temperature [K] at pressure P [Pa].
        Q=0: bubble point, Q=1: dew point.
        For pseudo-pure fluids like R410A, Q must be 0 or 1.
        Default Q=1 (dew) for evaporating temperature convention.
        """
        return CP.PropsSI("T", "P", P, "Q", Q, self.fluid)

    def P_sat(self, T, Q=1):
        """Saturation pressure [Pa] at temperature T [K].
        Q=0: bubble, Q=1: dew.
        For pseudo-pure fluids like R410A, Q must be 0 or 1.
        """
        return CP.PropsSI("P", "T", T, "Q", Q, self.fluid)

    # --- Density ---

    def rho(self, T, P):
        """Density [kg/m³] at T [K], P [Pa] (single-phase)."""
        return CP.PropsSI("D", "T", T, "P", P, self.fluid)

    def rho_sat_liquid(self, P):
        """Saturated liquid density [kg/m³] at P [Pa]."""
        return CP.PropsSI("D", "P", P, "Q", 0, self.fluid)

    def rho_sat_vapor(self, P):
        """Saturated vapor density [kg/m³] at P [Pa]."""
        return CP.PropsSI("D", "P", P, "Q", 1, self.fluid)

    def rho_two_phase(self, P, x):
        """Two-phase mixture density [kg/m³] (homogeneous model)."""
        rho_l = self.rho_sat_liquid(P)
        rho_g = self.rho_sat_vapor(P)
        return 1.0 / (x / rho_g + (1.0 - x) / rho_l)

    # --- Enthalpy ---

    def h(self, T, P):
        """Specific enthalpy [J/kg] at T [K], P [Pa]."""
        return CP.PropsSI("H", "T", T, "P", P, self.fluid)

    def h_sat_liquid(self, P):
        """Saturated liquid enthalpy [J/kg] at P [Pa]."""
        return CP.PropsSI("H", "P", P, "Q", 0, self.fluid)

    def h_sat_vapor(self, P):
        """Saturated vapor enthalpy [J/kg] at P [Pa]."""
        return CP.PropsSI("H", "P", P, "Q", 1, self.fluid)

    def h_two_phase(self, P, x):
        """Two-phase enthalpy [J/kg]."""
        h_l = self.h_sat_liquid(P)
        h_g = self.h_sat_vapor(P)
        return h_l + x * (h_g - h_l)

    # --- Entropy ---

    def s(self, T, P):
        """Specific entropy [J/(kg·K)] at T [K], P [Pa]."""
        return CP.PropsSI("S", "T", T, "P", P, self.fluid)

    def s_sat_vapor(self, P):
        """Saturated vapor entropy [J/(kg·K)] at P [Pa]."""
        return CP.PropsSI("S", "P", P, "Q", 1, self.fluid)

    # --- Transport properties ---

    def mu(self, T, P):
        """Dynamic viscosity [Pa·s] at T [K], P [Pa]."""
        return CP.PropsSI("V", "T", T, "P", P, self.fluid)

    def mu_sat_liquid(self, P):
        """Saturated liquid viscosity [Pa·s]."""
        return CP.PropsSI("V", "P", P, "Q", 0, self.fluid)

    def mu_sat_vapor(self, P):
        """Saturated vapor viscosity [Pa·s]."""
        return CP.PropsSI("V", "P", P, "Q", 1, self.fluid)

    def k_thermal(self, T, P):
        """Thermal conductivity [W/(m·K)] at T [K], P [Pa]."""
        return CP.PropsSI("L", "T", T, "P", P, self.fluid)

    def k_sat_liquid(self, P):
        """Saturated liquid thermal conductivity [W/(m·K)]."""
        return CP.PropsSI("L", "P", P, "Q", 0, self.fluid)

    def k_sat_vapor(self, P):
        """Saturated vapor thermal conductivity [W/(m·K)]."""
        return CP.PropsSI("L", "P", P, "Q", 1, self.fluid)

    def sigma(self, T):
        """Surface tension [N/m] at saturation temperature T [K]."""
        return CP.PropsSI("I", "T", T, "Q", 0, self.fluid)

    def sigma_at_P(self, P):
        """Surface tension [N/m] at saturation pressure P [Pa]."""
        T = self.T_sat(P)
        return self.sigma(T)

    # --- Specific heats ---

    def cp(self, T, P):
        """Specific heat at constant pressure [J/(kg·K)]."""
        return CP.PropsSI("C", "T", T, "P", P, self.fluid)

    def cv(self, T, P):
        """Specific heat at constant volume [J/(kg·K)]."""
        return CP.PropsSI("O", "T", T, "P", P, self.fluid)

    def cp_sat_liquid(self, P):
        """Saturated liquid cp [J/(kg·K)]."""
        return CP.PropsSI("C", "P", P, "Q", 0, self.fluid)

    # --- Quality from enthalpy ---

    def quality(self, h, P):
        """Vapor quality from enthalpy h [J/kg] at pressure P [Pa].
        Returns <0 if subcooled, >1 if superheated.
        """
        h_l = self.h_sat_liquid(P)
        h_g = self.h_sat_vapor(P)
        return (h - h_l) / (h_g - h_l)

    # --- Isentropic compression ---

    def h_after_isentropic_compression(self, P_suction, T_suction, P_discharge):
        """Enthalpy [J/kg] after isentropic compression.
        Starting from (P_suction, T_suction) to P_discharge.
        """
        s_in = self.s(T_suction, P_suction)
        return CP.PropsSI("H", "P", P_discharge, "S", s_in, self.fluid)

    def T_from_Ph(self, P, h):
        """Temperature [K] from pressure and enthalpy."""
        return CP.PropsSI("T", "P", P, "H", h, self.fluid)

    def rho_from_Ph(self, P, h):
        """Density [kg/m³] from pressure and enthalpy."""
        return CP.PropsSI("D", "P", P, "H", h, self.fluid)
