"""
Two-point charge tuning method.

From Shen, Braun & Groll (2009) as used in Li & Shen (2024).

The segment-by-segment HX model prediction of condenser charge has systematic
error that depends on the void fraction model. This error is approximately
linear in the liquid coil length (percentage of condenser in subcooled region).

=== Eq. (2) of Li & Shen (2024) ===
ΔM_liqL = C + k_liqL × L_liq

=== Eq. (3) ===
M_corrected = M_simulated + ΔM_liqL

The constants C and k_liqL are determined from two operating points where
the actual charge is known. In the paper's split system case:
  DeltaCharge = 0.0367 * LiquidLength - 1.9154  (from Figure 2)

where LiquidLength is the percentage (80-100%) of condenser in liquid phase.

Reference: Shen, B., Braun, J.E. and Groll, E.A. (2009),
"Improved methodologies for simulating unitary air conditioners at
off-design conditions," Int. J. Refrigeration, 32(7), pp.1837-1849.
"""
import numpy as np


class ChargeTuning:
    """Two-point charge calibration for condenser charge prediction.

    Attributes
    ----------
    C : float — intercept of calibration equation [kg]
    k : float — slope of calibration equation [kg/%]
    """

    def __init__(self, C=0.0, k=0.0):
        self.C = C
        self.k = k

    @classmethod
    def from_two_points(cls, L_liq_1, delta_M_1, L_liq_2, delta_M_2):
        """Fit calibration from two operating points.

        Parameters
        ----------
        L_liq_1, L_liq_2 : float — liquid coil length [%] at two conditions
        delta_M_1, delta_M_2 : float — (actual_charge - simulated_charge) [kg]

        Returns
        -------
        ChargeTuning instance
        """
        if abs(L_liq_1 - L_liq_2) < 0.01:
            raise ValueError("Two calibration points must have different L_liq values")

        k = (delta_M_2 - delta_M_1) / (L_liq_2 - L_liq_1)
        C = delta_M_1 - k * L_liq_1
        return cls(C=C, k=k)

    @classmethod
    def from_paper_split_system(cls):
        """Use the regression from Figure 2 of Li & Shen (2024).

        DeltaCharge = 0.0367 * LiquidLength - 1.9154
        (units: DeltaCharge in lbm, LiquidLength in %)

        Converting to kg: multiply by 0.4536
        """
        # Paper gives: DeltaCharge [lbm] = 0.0367 * L_liq [%] - 1.9154
        k_lbm = 0.0367   # lbm per %
        C_lbm = -1.9154  # lbm

        k_kg = k_lbm * 0.45359237   # kg per %
        C_kg = C_lbm * 0.45359237   # kg

        return cls(C=C_kg, k=k_kg)

    def correction(self, L_liquid_pct):
        """Calculate charge correction [kg].

        === Eq. (2): ΔM = C + k × L_liq ===

        Parameters
        ----------
        L_liquid_pct : float — subcooled (liquid) length as % of total condenser

        Returns
        -------
        delta_M : float — charge correction [kg] (add to simulated charge)
        """
        return self.C + self.k * L_liquid_pct

    def correct_charge(self, M_simulated, L_liquid_pct):
        """Apply correction to simulated condenser charge.

        === Eq. (3): M_corrected = M_simulated + ΔM ===

        Parameters
        ----------
        M_simulated : float — simulated condenser charge [kg]
        L_liquid_pct : float — liquid length %

        Returns
        -------
        M_corrected : float — corrected charge [kg]
        """
        return M_simulated + self.correction(L_liquid_pct)
