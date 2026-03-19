"""
Void fraction models for two-phase refrigerant in heat exchangers.

The void fraction α determines the volume occupied by vapor in a two-phase
flow, which directly affects the refrigerant charge inventory calculation:
  M_two_phase = Σ [α·ρ_g + (1-α)·ρ_l] × A_cs × ΔL   per segment

The paper uses Rouhani & Axelsson (1970), which is the HPDM default.

=== Rouhani & Axelsson (1970) void fraction ===
α = (x/ρ_g) × { [1 + 0.12(1-x)] × [x/ρ_g + (1-x)/ρ_l]
    + 1.18(1-x) × [g·σ·(ρ_l-ρ_g)]^0.25 / (G·ρ_l^0.5) }^(-1)

Reference: Rouhani, S.Z. and Axelsson, E., "Calculation of void volume
fraction in the subcooled and quality boiling regions,"
Int. J. Heat Mass Transfer, 13, pp. 383-393, 1970.
"""
import numpy as np

G_ACCEL = 9.81  # m/s², gravitational acceleration


def rouhani_axelsson(x, rho_l, rho_g, sigma, G_mass_flux):
    """Rouhani-Axelsson (1970) drift-flux void fraction model.

    This is the default void fraction model in HPDM and the one used in
    Li & Shen (2024) for condenser charge prediction.

    Parameters
    ----------
    x : float — vapor quality [-], 0 < x < 1
    rho_l : float — saturated liquid density [kg/m³]
    rho_g : float — saturated vapor density [kg/m³]
    sigma : float — surface tension [N/m]
    G_mass_flux : float — mass flux [kg/(m²·s)]

    Returns
    -------
    alpha : float — void fraction [-], 0 < α < 1
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if G_mass_flux < 1e-6:
        # Stagnant — use homogeneous model
        return homogeneous(x, rho_l, rho_g)

    # === Rouhani-Axelsson correlation ===
    term1 = (1.0 + 0.12 * (1.0 - x)) * (x / rho_g + (1.0 - x) / rho_l)
    term2 = (1.18 * (1.0 - x)
             * (G_ACCEL * sigma * (rho_l - rho_g))**0.25
             / (G_mass_flux * rho_l**0.5))
    denominator = term1 + term2
    alpha = (x / rho_g) / denominator

    return np.clip(alpha, 0.0, 1.0)


def homogeneous(x, rho_l, rho_g):
    """Homogeneous void fraction model (simplest, assumes equal phase velocities).

    α = 1 / (1 + (1-x)/x × ρ_g/ρ_l)
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return 1.0 / (1.0 + (1.0 - x) / x * rho_g / rho_l)


def premoli(x, rho_l, rho_g, sigma, G_mass_flux, D_h, mu_l):
    """Premoli et al. (1971) CISE void fraction model.

    Alternative model available in HPDM. More complex but accounts for
    surface tension effects in small tubes.

    Parameters
    ----------
    x : float — vapor quality
    rho_l, rho_g : float — phase densities [kg/m³]
    sigma : float — surface tension [N/m]
    G_mass_flux : float — mass flux [kg/(m²·s)]
    D_h : float — hydraulic diameter [m]
    mu_l : float — liquid dynamic viscosity [Pa·s]

    Returns
    -------
    alpha : float — void fraction [-]
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    beta = homogeneous(x, rho_l, rho_g)  # homogeneous void fraction
    y = beta / (1.0 - beta)  # volumetric quality ratio

    # Dimensionless groups
    Re_l = G_mass_flux * D_h / mu_l
    We_l = G_mass_flux**2 * D_h / (sigma * rho_l)

    # Premoli correlation parameters
    F1 = 1.578 * Re_l**(-0.19) * (rho_l / rho_g)**0.22
    F2 = 0.0273 * We_l * Re_l**(-0.51) * (rho_l / rho_g)**(-0.08)

    # Slip ratio
    S = 1.0 + F1 * (y / (1.0 + y * F2) - y * F2)**0.5 if y > 0 else 1.0
    S = max(S, 1.0)

    alpha = 1.0 / (1.0 + (1.0 - x) / x * rho_g / rho_l * S)
    return np.clip(alpha, 0.0, 1.0)


def two_phase_density(alpha, rho_l, rho_g):
    """Average two-phase density [kg/m³] from void fraction.

    ρ_tp = α × ρ_g + (1 - α) × ρ_l

    This is the density used for charge inventory calculations.
    """
    return alpha * rho_g + (1.0 - alpha) * rho_l


def charge_in_two_phase_segment(x, rho_l, rho_g, sigma, G_mass_flux,
                                 A_cs, length, void_model="rouhani"):
    """Refrigerant mass in a two-phase segment [kg].

    M = ρ_tp × A_cs × L = [α·ρ_g + (1-α)·ρ_l] × A_cs × L

    Parameters
    ----------
    x : float — average vapor quality in segment
    rho_l, rho_g : float — saturated phase densities [kg/m³]
    sigma : float — surface tension [N/m]
    G_mass_flux : float — mass flux [kg/(m²·s)]
    A_cs : float — flow cross-section area [m²]
    length : float — segment length [m]
    void_model : str — "rouhani" (default) or "homogeneous"

    Returns
    -------
    M : float — refrigerant mass [kg]
    """
    if void_model == "rouhani":
        alpha = rouhani_axelsson(x, rho_l, rho_g, sigma, G_mass_flux)
    elif void_model == "homogeneous":
        alpha = homogeneous(x, rho_l, rho_g)
    else:
        raise ValueError(f"Unknown void fraction model: {void_model}")

    rho_tp = two_phase_density(alpha, rho_l, rho_g)
    return rho_tp * A_cs * length
