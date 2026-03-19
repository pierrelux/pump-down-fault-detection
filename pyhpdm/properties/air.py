"""
Moist air psychrometric properties.

Used for air-side heat transfer calculations in heat exchangers.
Follows ASHRAE Handbook of Fundamentals correlations.

Key properties:
- Dry-air enthalpy, humidity ratio at saturation
- Wet-bulb temperature
- Enthalpy-based driving potential for wet coils (Braun et al. 1989)
"""
import numpy as np

# Constants
P_ATM = 101325.0  # Pa, standard atmosphere
C_PA = 1006.0     # J/(kg·K), dry air specific heat
C_PV = 1860.0     # J/(kg·K), water vapor specific heat
H_FG0 = 2501000.0 # J/kg, latent heat of vaporization at 0°C
R_AIR = 287.055    # J/(kg·K), gas constant for dry air


def saturation_pressure(T):
    """Water saturation pressure [Pa] at temperature T [K].
    ASHRAE correlation (valid -100 to 200 °C).
    """
    T_C = T - 273.15
    if T_C >= 0:
        # Antoine-like equation for T >= 0°C
        ln_p = (
            -5.8002206e3 / T
            + 1.3914993
            - 4.8640239e-2 * T
            + 4.1764768e-5 * T**2
            - 1.4452093e-8 * T**3
            + 6.5459673 * np.log(T)
        )
    else:
        # Ice region
        ln_p = (
            -5.6745359e3 / T
            + 6.3925247
            - 9.677843e-3 * T
            + 6.2215701e-7 * T**2
            + 2.0747825e-9 * T**3
            - 9.484024e-13 * T**4
            + 4.1635019 * np.log(T)
        )
    return np.exp(ln_p)


def humidity_ratio_sat(T, P=P_ATM):
    """Saturation humidity ratio [kg_water/kg_dry_air] at T [K], P [Pa]."""
    p_ws = saturation_pressure(T)
    return 0.62198 * p_ws / (P - p_ws)


def enthalpy_moist_air(T, W):
    """Moist air enthalpy [J/kg_dry_air] at T [K] and humidity ratio W.
    Reference: 0°C dry air.
    """
    T_C = T - 273.15
    return C_PA * T_C + W * (H_FG0 + C_PV * T_C)


def enthalpy_saturated_air(T, P=P_ATM):
    """Enthalpy of saturated moist air [J/kg_dry_air] at T [K]."""
    W_sat = humidity_ratio_sat(T, P)
    return enthalpy_moist_air(T, W_sat)


def wet_bulb_temperature(T_db, W, P=P_ATM, tol=0.01):
    """Wet-bulb temperature [K] by iterative solution.
    T_db: dry-bulb temperature [K]
    W: humidity ratio [kg/kg]
    """
    T_wb = T_db - 5.0  # initial guess
    for _ in range(50):
        W_sat_wb = humidity_ratio_sat(T_wb, P)
        h_air = enthalpy_moist_air(T_db, W)
        h_sat_wb = enthalpy_moist_air(T_wb, W_sat_wb)
        # Energy balance: h_air = h_sat_wb - (W_sat_wb - W) * h_fg(T_wb)
        h_fg_wb = H_FG0 + C_PV * (T_wb - 273.15)
        h_calc = h_sat_wb - (W_sat_wb - W) * h_fg_wb
        err = h_air - h_calc
        if abs(err) < tol:
            break
        # Newton step (approximate derivative)
        T_wb += err / (C_PA + W * C_PV)
    return T_wb


def dew_point_temperature(W, P=P_ATM):
    """Dew point temperature [K] from humidity ratio W."""
    p_w = W * P / (0.62198 + W)
    # Invert saturation pressure: binary search
    T_lo, T_hi = 200.0, 373.0
    for _ in range(60):
        T_mid = (T_lo + T_hi) / 2.0
        if saturation_pressure(T_mid) < p_w:
            T_lo = T_mid
        else:
            T_hi = T_mid
    return (T_lo + T_hi) / 2.0


def density_moist_air(T, W, P=P_ATM):
    """Moist air density [kg/m³]."""
    return P / (R_AIR * T * (1.0 + 1.6078 * W))
