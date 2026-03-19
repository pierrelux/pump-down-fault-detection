#!/usr/bin/env python3
"""
Reproduce all figures from Li, Shen, Welch & Gluesenkamp (2024),
"A Refrigerant Charge Prediction Method Based on Pump Down Operation."

Generates:
  - Fig 7:  Predicted vs Measured charge (3-ton split, 10 validation cases)
  - Fig 8:  Charge migration during pump-down (5-ton system)
  - Fig 9:  Suction pressure during pump-down (5-ton system)
  - Fig 10: Mass flow rate during pump-down (5-ton system)

Usage:
    cd pumpdown && python reproduce_all.py
"""

import sys
import os
import numpy as np

import matplotlib
matplotlib.use("Agg")

# --- Path setup ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from scipy.optimize import brentq

from pyhpdm.properties.refrigerant import (
    Refrigerant, F_to_K, K_to_F, psi_to_Pa, Pa_to_psi, LBM_TO_KG,
)
from pyhpdm.components.compressor import CompressorMap
from pyhpdm.components.valve import estimate_Cv_from_figure6
from pyhpdm.charge.pump_down import simulate_pump_down

from src import units
from src.plot_paper_figures import plot_fig7, plot_fig8, plot_fig9, plot_fig10


# ============================================================================
# 5-Ton System Parameters (Paper Section 3.1, Figs 8-10)
# ============================================================================

# Base AHRI 10-coefficient map from HPDM scrape (3-ton compressor)
_COEFFS_MDOT_3TON = [
    176.0, 2.72, -2.12, 0.0172, -0.0112, 0.0181,
    6.52e-5, 1.08e-5, 4.00e-5, -5.54e-5,
]
_COEFFS_POWER_3TON = [
    1590.0, 6.79, -34.9, -0.226, -0.0660, 0.388,
    -1.37e-5, 1.01e-3, 7.41e-4, -1.12e-3,
]

# 5-ton ZP61 compressor displacement and speed
V_DISP_5TON = 57.02e-6   # m^3/rev
N_RPM_5TON = 3500.0

# Displacement x speed ratio (reference; actual scale is calibrated below)
_V_DISP_3TON = 0.000501302 * 0.0283168  # m^3/rev
_N_RPM_3TON = 3600.0
_DISP_RATIO = (V_DISP_5TON * N_RPM_5TON) / (_V_DISP_3TON * _N_RPM_3TON)

# System conditions from paper
M_TOTAL_LBM = 13.28      # total refrigerant charge [lbm]
M_LP_INIT_LBM = 5.81     # initial low-side charge [lbm] (Fig 8)
T_INDOOR_F = 75.0         # indoor temperature [degF]
T_OUTDOOR_F = 95.0        # outdoor temperature [degF]
P_CUTOFF_PSIA = 55.0      # low-pressure cutoff [psia] (Fig 9 annotation)
TARGET_DURATION = 24.0     # pump-down duration [s]

# LP-side volume (nominal for 5-ton: evaporator + suction + liquid line)
V_LP_5TON = 0.010         # m^3 (10 L)

# Initial quality in LP side (two-phase average)
X_INITIAL = 0.2

# 4-way valve leakage coefficient
CV_VALVE = estimate_Cv_from_figure6()


# ============================================================================
# Compressor factory and pump-down helpers
# ============================================================================

def _make_compressor(scale):
    """Create a 5-ton compressor with scaled AHRI map coefficients."""
    return CompressorMap(
        coeffs_mdot=[c * scale for c in _COEFFS_MDOT_3TON],
        coeffs_power=[c * scale for c in _COEFFS_POWER_3TON],
        V_displacement=V_DISP_5TON,
        N_rpm=N_RPM_5TON,
        refrigerant="R410A",
        T_sh_rated_K=11.1,
        F_mass=0.75,
    )


def _run_pumpdown(compressor, ref, V_LP=V_LP_5TON):
    """Run pump-down simulation, return PumpDownResult."""
    T_indoor_K = F_to_K(T_INDOOR_F)
    T_outdoor_K = F_to_K(T_OUTDOOR_F)
    return simulate_pump_down(
        compressor=compressor,
        Cv_valve=CV_VALVE,
        P_suction_initial_Pa=ref.P_sat(T_indoor_K),
        P_discharge_initial_Pa=ref.P_sat(T_outdoor_K + 15.0),
        T_outdoor_K=T_outdoor_K,
        V_LP_m3=V_LP,
        ref=ref,
        M_LP_initial_kg=units.lbm_to_kg(M_LP_INIT_LBM),
        P_low_cutoff_Pa=psi_to_Pa(P_CUTOFF_PSIA),
        dt=0.5,
        max_time=200.0,
        T_superheat_initial_K=5.0,
        x_initial=X_INITIAL,
    )


def calibrate_compressor(ref):
    """Find the mass-flow scale factor that yields TARGET_DURATION.

    The AHRI map coefficients are for a 3-ton compressor.  We scale them
    to approximate a 5-ton unit.  The exact displacement ratio (3.91)
    overshoots because the simple two-phase model doesn't capture the
    real-world mass-flow decrease during pump-down.  Instead, we
    calibrate the scale via brentq for the correct duration.
    """
    def residual(log_scale):
        comp = _make_compressor(np.exp(log_scale))
        pd = _run_pumpdown(comp, ref)
        return pd.duration - TARGET_DURATION

    log_s = brentq(residual, np.log(1.0), np.log(8.0), xtol=0.01)
    scale = np.exp(log_s)
    return _make_compressor(scale), scale


def extract_time_series(pd_result, m_total_kg):
    """Extract numpy arrays from PumpDownResult for plotting."""
    states = pd_result.states
    time = np.array([s.time for s in states])
    m_low = np.array([s.M_LP for s in states])
    m_high = m_total_kg - m_low
    P_suction = np.array([s.P_suction for s in states])
    mdot = np.array([s.m_dot_compressor for s in states])
    return dict(time=time, m_low=m_low, m_high=m_high,
                P_suction=P_suction, mdot=mdot)


# ============================================================================
# Fig 8-10: 5-ton pump-down simulation
# ============================================================================

def run_5ton_pumpdown():
    """Run the 5-ton pump-down simulation for Figs 8-10."""
    print("=" * 60)
    print("5-TON SYSTEM: Pump-Down Simulation (Figs 8-10)")
    print("=" * 60)

    ref = Refrigerant("R410A")

    print(f"\nCalibrating compressor scale for {TARGET_DURATION:.0f}s duration...")
    print(f"  Displacement ratio (reference): {_DISP_RATIO:.2f}")
    compressor, scale = calibrate_compressor(ref)
    print(f"  Calibrated scale factor: {scale:.2f}")

    # Verify initial mass flow
    Te_F = T_INDOOR_F
    Tc_F = K_to_F(F_to_K(T_OUTDOOR_F) + 15.0)
    mdot0 = compressor.mass_flow_kg_s(Te_F, Tc_F)
    print(f"  Initial mdot at Te={Te_F:.0f}F, Tc={Tc_F:.0f}F: "
          f"{units.kg_s_to_lbm_s(mdot0):.3f} lbm/s (paper: ~0.40)")

    # Run final simulation
    pd = _run_pumpdown(compressor, ref)
    m_total_kg = units.lbm_to_kg(M_TOTAL_LBM)
    ts = extract_time_series(pd, m_total_kg)

    # Summary
    print(f"\nResults:")
    print(f"  Duration:       {pd.duration:.1f} s ({pd.terminated_by})")
    print(f"  Initial P_suc:  {Pa_to_psi(ts['P_suction'][0]):.1f} psia")
    print(f"  Final P_suc:    {Pa_to_psi(ts['P_suction'][-1]):.1f} psia")
    print(f"  Initial mdot:   {units.kg_s_to_lbm_s(ts['mdot'][0]):.3f} lbm/s")
    print(f"  Final mdot:     {units.kg_s_to_lbm_s(ts['mdot'][-1]):.3f} lbm/s")
    print(f"  Initial m_low:  {units.kg_to_lbm(ts['m_low'][0]):.2f} lbm")
    print(f"  Final m_low:    {units.kg_to_lbm(ts['m_low'][-1]):.2f} lbm")
    print(f"  V_LP:           {V_LP_5TON*1000:.1f} L")

    return ts, pd.duration


# ============================================================================
# Fig 7: 3-ton charge prediction validation
# ============================================================================

def run_3ton_validation():
    """Run the 3-ton validation (10-case test matrix) for Fig 7."""
    from reproduce_paper import main as run_reproduction
    return run_reproduction()


# ============================================================================
# Comparison summary
# ============================================================================

def print_comparison(ts, duration):
    """Print comparison of key model values against paper."""
    print("\n" + "=" * 60)
    print("COMPARISON WITH PAPER VALUES")
    print("=" * 60)
    fmt = "  {:<25} {:>10} {:>10} {:>8}"
    print(fmt.format("Parameter", "Model", "Paper", "Unit"))
    print("  " + "-" * 55)
    rows = [
        ("P_suc initial", f"{Pa_to_psi(ts['P_suction'][0]):.1f}", "~250", "psia"),
        ("P_suc final", f"{Pa_to_psi(ts['P_suction'][-1]):.1f}", "55", "psia"),
        ("Duration", f"{duration:.1f}", "24", "s"),
        ("mdot initial", f"{units.kg_s_to_lbm_s(ts['mdot'][0]):.3f}", "~0.40", "lbm/s"),
        ("m_low initial", f"{units.kg_to_lbm(ts['m_low'][0]):.2f}", "5.81", "lbm"),
    ]
    for name, model, paper, unit in rows:
        print(fmt.format(name, model, paper, unit))


# ============================================================================
# Main
# ============================================================================

def main():
    fig_dir = os.path.join(SCRIPT_DIR, "figures", "reproduced")
    os.makedirs(fig_dir, exist_ok=True)

    # --- Figs 8-10: 5-ton pump-down ---
    ts, duration = run_5ton_pumpdown()
    plot_fig8(ts, os.path.join(fig_dir, "fig8_charge_migration.png"))
    plot_fig9(ts, os.path.join(fig_dir, "fig9_suction_pressure.png"))
    plot_fig10(ts, os.path.join(fig_dir, "fig10_mass_flow_rate.png"))
    print_comparison(ts, duration)

    # --- Fig 7: 3-ton validation ---
    print("\n" + "=" * 60)
    print("3-TON SYSTEM: Charge Prediction Validation (Fig 7)")
    print("=" * 60)
    try:
        results = run_3ton_validation()
        if results:
            plot_fig7(results, os.path.join(fig_dir, "fig7_predicted_vs_measured.png"))
            errors = [abs(r["error_pct"]) for r in results]
            print(f"\nFig 7 Statistics:")
            print(f"  Mean |error|: {np.mean(errors):.1f}%")
            print(f"  Max |error|:  {np.max(errors):.1f}%")
            print(f"  Within +/-8%: {sum(1 for e in errors if e <= 8.0)}/{len(errors)}")
    except Exception as e:
        print(f"\n  Fig 7 generation failed: {e}")
        import traceback
        traceback.print_exc()

    print(f"\nAll figures saved to {fig_dir}/")


if __name__ == "__main__":
    main()
