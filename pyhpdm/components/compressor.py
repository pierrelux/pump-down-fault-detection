"""
Compressor model: AHRI 10-coefficient polynomial map.

Implements the standard AHRI 540 compressor performance representation used in HPDM.
The map gives mass flow rate and power as bicubic polynomials of evaporating and
condensing saturation temperatures.

=== AHRI 10-coefficient map (ORNL/CON-343, ACEEE 2017 slides) ===
Y = C[0] + C[1]*Te + C[2]*Tc + C[3]*Te² + C[4]*Te*Tc
  + C[5]*Tc² + C[6]*Te³ + C[7]*Tc*Te² + C[8]*Te*Tc² + C[9]*Tc³

Where:
  Te = evaporating saturation temperature [°F]
  Tc = condensing saturation temperature [°F]
  Y  = mass flow rate [lbm/h] or power [W]

The volumetric efficiency is derived from the map mass flow:
  η_vol = ṁ_map / (V_disp * ρ_suction * N/60)  — Eq. (4) of Li & Shen (2024)

DEVIATION DEV-002: Compressor map coefficients are not published in the paper.
See DEVIATIONS.md.
"""
import numpy as np
from ..properties.refrigerant import Refrigerant, F_to_K, K_to_F, LBM_PER_H_TO_KG_PER_S


def ahri_10_coeff(Te_F, Tc_F, coeffs):
    """Evaluate the AHRI 10-coefficient polynomial.

    === AHRI 540 standard map equation ===
    Y = C[0] + C[1]*Te + C[2]*Tc + C[3]*Te² + C[4]*Te*Tc
      + C[5]*Tc² + C[6]*Te³ + C[7]*Tc*Te² + C[8]*Te*Tc² + C[9]*Tc³

    Parameters
    ----------
    Te_F : float — evaporating saturation temperature [°F]
    Tc_F : float — condensing saturation temperature [°F]
    coeffs : array-like of 10 floats — polynomial coefficients

    Returns
    -------
    Y : float — mass flow [lbm/h] or power [W] depending on coefficients
    """
    C = coeffs
    Te, Tc = Te_F, Tc_F
    return (C[0]
            + C[1] * Te + C[2] * Tc
            + C[3] * Te**2 + C[4] * Te * Tc + C[5] * Tc**2
            + C[6] * Te**3 + C[7] * Tc * Te**2 + C[8] * Te * Tc**2 + C[9] * Tc**3)


class CompressorMap:
    """AHRI 10-coefficient compressor model.

    Attributes
    ----------
    coeffs_mdot : array(10) — mass flow coefficients [lbm/h]
    coeffs_power : array(10) — power coefficients [W]
    V_displacement : float — swept volume [m³/rev]
    N_rpm : float — compressor speed [rpm]
    ref : Refrigerant — refrigerant object
    T_sh_rated : float — rated superheat at map conditions [K] (default 11.1 K = 20°F)
    F_mass : float — superheat correction mass factor (default 0.75, from ACEEE 2017)
    """

    def __init__(self, coeffs_mdot, coeffs_power, V_displacement, N_rpm,
                 refrigerant="R410A", T_sh_rated_K=11.1, F_mass=0.75,
                 heat_gain_ratio=0.9):
        self.coeffs_mdot = np.array(coeffs_mdot, dtype=float)
        self.coeffs_power = np.array(coeffs_power, dtype=float)
        self.V_displacement = V_displacement  # m³/rev
        self.N_rpm = N_rpm                    # rev/min
        self.ref = Refrigerant(refrigerant)
        self.T_sh_rated_K = T_sh_rated_K
        self.F_mass = F_mass
        self.heat_gain_ratio = heat_gain_ratio  # fraction of power absorbed by refrigerant

    def mass_flow_map(self, Te_F, Tc_F):
        """Map mass flow rate [lbm/h] at (Te, Tc) in °F."""
        return ahri_10_coeff(Te_F, Tc_F, self.coeffs_mdot)

    def power_map(self, Te_F, Tc_F):
        """Map power [W] at (Te, Tc) in °F."""
        return ahri_10_coeff(Te_F, Tc_F, self.coeffs_power)

    def mass_flow_kg_s(self, Te_F, Tc_F, T_superheat_K=None):
        """Actual refrigerant mass flow rate [kg/s].

        If T_superheat_K differs from the rated superheat, applies the
        superheat correction from ACEEE 2017 / ORNL/CON-343:
          ṁ_actual = ṁ_map × (v_rated / v_actual) × F_mass + ṁ_map × (1 - F_mass)

        where v = specific volume at suction, and F_mass ~ 0.75 for reciprocating.
        """
        mdot_map_lbm_h = self.mass_flow_map(Te_F, Tc_F)
        mdot_map = mdot_map_lbm_h * LBM_PER_H_TO_KG_PER_S  # kg/s

        if T_superheat_K is not None and abs(T_superheat_K - self.T_sh_rated_K) > 0.1:
            # Superheat correction
            T_evap_K = F_to_K(Te_F)
            P_evap = self.ref.P_sat(T_evap_K)

            T_suc_rated = T_evap_K + self.T_sh_rated_K
            T_suc_actual = T_evap_K + T_superheat_K

            v_rated = 1.0 / self.ref.rho(T_suc_rated, P_evap)
            v_actual = 1.0 / self.ref.rho(T_suc_actual, P_evap)

            correction = (v_rated / v_actual) * self.F_mass + (1.0 - self.F_mass)
            mdot_map *= correction

        return mdot_map

    def power_W(self, Te_F, Tc_F):
        """Compressor shaft power [W]."""
        return self.power_map(Te_F, Tc_F)

    def volumetric_efficiency(self, Te_F, Tc_F, T_superheat_K=None):
        """Volumetric efficiency [-] derived from map.

        === Derived from Eq. (4) of Li & Shen (2024) ===
        η_vol = ṁ / (V_disp × ρ_suction × N/60)

        where ṁ is the map mass flow at rated superheat.
        """
        mdot = self.mass_flow_kg_s(Te_F, Tc_F, T_superheat_K)

        T_evap_K = F_to_K(Te_F)
        P_evap = self.ref.P_sat(T_evap_K)
        T_sh = T_superheat_K if T_superheat_K is not None else self.T_sh_rated_K
        T_suc = T_evap_K + T_sh
        rho_suc = self.ref.rho(T_suc, P_evap)

        # V_disp * N/60 = volumetric displacement rate [m³/s]
        V_dot = self.V_displacement * self.N_rpm / 60.0
        m_dot_ideal = rho_suc * V_dot

        if m_dot_ideal < 1e-12:
            return 0.0
        return mdot / m_dot_ideal

    def isentropic_efficiency(self, Te_F, Tc_F, T_superheat_K=None):
        """Isentropic efficiency [-] derived from map.

        η_isen = ṁ × (h_2s - h_1) / P_comp
        """
        mdot = self.mass_flow_kg_s(Te_F, Tc_F, T_superheat_K)
        power = self.power_W(Te_F, Tc_F)

        T_evap_K = F_to_K(Te_F)
        T_cond_K = F_to_K(Tc_F)
        P_evap = self.ref.P_sat(T_evap_K)
        P_cond = self.ref.P_sat(T_cond_K)

        T_sh = T_superheat_K if T_superheat_K is not None else self.T_sh_rated_K
        T_suc = T_evap_K + T_sh
        h_1 = self.ref.h(T_suc, P_evap)
        h_2s = self.ref.h_after_isentropic_compression(P_evap, T_suc, P_cond)

        if power < 1.0:
            return 0.0
        return mdot * (h_2s - h_1) / power

    def discharge_state(self, Te_F, Tc_F, T_superheat_K=None):
        """Compute discharge temperature and enthalpy.

        Returns (T_discharge [K], h_discharge [J/kg], P_discharge [Pa])
        """
        mdot = self.mass_flow_kg_s(Te_F, Tc_F, T_superheat_K)
        power = self.power_W(Te_F, Tc_F)

        T_evap_K = F_to_K(Te_F)
        T_cond_K = F_to_K(Tc_F)
        P_evap = self.ref.P_sat(T_evap_K)
        P_cond = self.ref.P_sat(T_cond_K)

        T_sh = T_superheat_K if T_superheat_K is not None else self.T_sh_rated_K
        T_suc = T_evap_K + T_sh
        h_1 = self.ref.h(T_suc, P_evap)

        # Energy balance: h_2 = h_1 + P_comp * heat_gain_ratio / ṁ
        # heat_gain_ratio < 1 models shell heat loss (HPDM default: 0.9)
        if mdot > 1e-12:
            h_2 = h_1 + power * self.heat_gain_ratio / mdot
        else:
            h_2 = h_1

        T_dis = self.ref.T_from_Ph(P_cond, h_2)
        return T_dis, h_2, P_cond


def mass_flow_during_pumpdown(compressor, P_suction_Pa, P_discharge_Pa, T_suction_K):
    """Calculate compressor mass flow during pump-down.

    === Eq. (4) of Li & Shen (2024) ===
    Mr_compressor = V_displacement × ρ_suction × η_volumetric

    During pump-down, the evaporating pressure drops while the condensing
    pressure stays approximately constant. We compute η_vol from the map
    at the instantaneous (T_evap_sat, T_cond_sat).

    Parameters
    ----------
    compressor : CompressorMap
    P_suction_Pa : float — instantaneous suction pressure [Pa]
    P_discharge_Pa : float — instantaneous discharge pressure [Pa]
    T_suction_K : float — suction temperature [K]

    Returns
    -------
    m_dot : float — mass flow rate [kg/s]
    eta_vol : float — volumetric efficiency [-]
    """
    ref = compressor.ref

    # Saturation temperatures from pressures
    T_evap_K = ref.T_sat(P_suction_Pa)
    T_cond_K = ref.T_sat(P_discharge_Pa)
    Te_F = K_to_F(T_evap_K)
    Tc_F = K_to_F(T_cond_K)

    # Actual superheat
    T_sh_K = T_suction_K - T_evap_K

    # Volumetric efficiency from map
    eta_vol = compressor.volumetric_efficiency(Te_F, Tc_F, T_sh_K)
    eta_vol = max(eta_vol, 0.0)  # cannot be negative

    # Suction density at actual conditions
    rho_suc = ref.rho(T_suction_K, P_suction_Pa)

    # Eq. (4): Mr = V_disp * rho_suc * eta_vol * (N/60)
    V_dot = compressor.V_displacement * compressor.N_rpm / 60.0
    m_dot = V_dot * rho_suc * eta_vol

    return m_dot, eta_vol
