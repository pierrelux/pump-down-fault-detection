"""Imperial <-> SI conversion utilities for refrigeration calculations."""

# Pressure
PSI_TO_PA = 6894.757293168  # 1 psi = 6894.76 Pa
ATM_PSI = 14.696  # 1 atm in psi


def psig_to_pa(psig: float) -> float:
    """Gauge pressure (psig) to absolute pressure (Pa)."""
    return (psig + ATM_PSI) * PSI_TO_PA


def pa_to_psig(pa: float) -> float:
    """Absolute pressure (Pa) to gauge pressure (psig)."""
    return pa / PSI_TO_PA - ATM_PSI


def psi_to_pa(psi: float) -> float:
    """Absolute psi to Pa."""
    return psi * PSI_TO_PA


def pa_to_psi(pa: float) -> float:
    """Pa to absolute psi."""
    return pa / PSI_TO_PA


# Temperature
def f_to_k(f: float) -> float:
    """Fahrenheit to Kelvin."""
    return (f - 32) * 5 / 9 + 273.15


def k_to_f(k: float) -> float:
    """Kelvin to Fahrenheit."""
    return (k - 273.15) * 9 / 5 + 32


# Mass
LBM_TO_KG = 0.45359237


def lbm_to_kg(lbm: float) -> float:
    return lbm * LBM_TO_KG


def kg_to_lbm(kg: float) -> float:
    return kg / LBM_TO_KG


# Mass flow rate
def lbm_s_to_kg_s(lbm_s: float) -> float:
    return lbm_s * LBM_TO_KG


def kg_s_to_lbm_s(kg_s: float) -> float:
    return kg_s / LBM_TO_KG


# Energy
BTU_LBM_TO_J_KG = 2326.0  # 1 Btu/lbm = 2326 J/kg

# Volume
FT3_TO_M3 = 0.028316846592
