"""Paper-style figure plotting for Li, Shen, Welch & Gluesenkamp (2024)."""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import units


def plot_fig7(results, save_path):
    """Fig 7: Predicted vs Measured Charge [lbm], 3-ton split system.

    Scatter plot with 45-degree line and +/-8% dashed bands,
    color-coded by charge level.
    """
    fig, ax = plt.subplots(figsize=(7, 7))

    colors = {7.0: "#1f77b4", 8.08: "#d62728", 9.11: "#2ca02c"}
    labels_map = {7.0: "7.0 lbm", 8.08: "8.08 lbm", 9.11: "9.11 lbm"}
    plotted = set()

    for r in results:
        clbm = r["charge_actual_lbm"]
        c = colors.get(clbm, "gray")
        lbl = labels_map.get(clbm) if clbm not in plotted else None
        plotted.add(clbm)
        ax.scatter(
            r["charge_actual_lbm"], r["charge_predicted_lbm"],
            color=c, s=80, zorder=5, edgecolors="k", linewidth=0.5,
            label=lbl,
        )

    mn, mx = 6.0, 10.0
    ax.plot([mn, mx], [mn, mx], "k-", lw=1.5, label="Perfect prediction")
    ax.plot([mn, mx], [mn * 1.08, mx * 1.08], "k--", lw=0.8, alpha=0.4, label="\u00b18%")
    ax.plot([mn, mx], [mn * 0.92, mx * 0.92], "k--", lw=0.8, alpha=0.4)
    ax.fill_between(
        [mn, mx], [mn * 0.92, mx * 0.92], [mn * 1.08, mx * 1.08],
        alpha=0.08, color="gray",
    )

    ax.set_xlabel("Measured Charge [lbm]", fontsize=12)
    ax.set_ylabel("Predicted Charge [lbm]", fontsize=12)
    ax.set_title("Fig 7: Predicted vs Measured Charge", fontsize=13)
    ax.set_xlim(mn, mx)
    ax.set_ylim(mn, mx)
    ax.set_aspect("equal")
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  Saved {save_path}")


def plot_fig8(ts, save_path):
    """Fig 8: Charge migration during pump-down [lbm] vs time [s].

    Blue circles: total, Purple triangles: high-side, Orange squares: low-side.
    """
    t = ts["time"]
    m_total_lbm = units.kg_to_lbm(ts["m_low"] + ts["m_high"])
    m_high_lbm = units.kg_to_lbm(ts["m_high"])
    m_low_lbm = units.kg_to_lbm(ts["m_low"])

    every = max(1, len(t) // 25)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(t, m_total_lbm, "bo-", ms=4, label="Charge_total", markevery=every)
    ax.plot(t, m_high_lbm, "m^-", ms=4, label="Charge_highSide", markevery=every)
    ax.plot(
        t, m_low_lbm, "s-", color="orange", ms=4,
        label="Charge_lowSide", markevery=every,
    )

    t_end = t[-1]
    ax.axvline(t_end, color="red", ls="--", alpha=0.7)
    ax.annotate(
        f"t = {t_end:.0f} s", xy=(t_end, 1), fontsize=9, color="red",
        ha="right", xytext=(-5, 5), textcoords="offset points",
    )

    ax.set_xlabel("Time Step [s]", fontsize=12)
    ax.set_ylabel("Charge [lbm]", fontsize=12)
    ax.set_title("Fig 8: Charge Migration During Pump-Down", fontsize=13)
    ax.set_xlim(0, max(t) + 2)
    ax.set_ylim(0, 14)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  Saved {save_path}")


def plot_fig9(ts, save_path):
    """Fig 9: Suction pressure [psia] during pump-down."""
    t = ts["time"]
    P_psia = units.pa_to_psi(ts["P_suction"])
    every = max(1, len(t) // 25)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(t, P_psia, "go-", ms=4, label="Suction Pressure", markevery=every)

    t_end = t[-1]
    ax.axvline(t_end, color="red", ls="--", alpha=0.7)
    ax.annotate(
        f"Psuc={P_psia[-1]:.0f} psia, {t_end:.0f} s",
        xy=(t_end, P_psia[-1]), fontsize=9, color="red",
        xytext=(-10, 20), textcoords="offset points",
        arrowprops=dict(arrowstyle="->", color="red", lw=0.8),
    )

    ax.set_xlabel("Time Step [s]", fontsize=12)
    ax.set_ylabel("Suction Pressure [psi]", fontsize=12)
    ax.set_title("Fig 9: Suction Pressure During Pump-Down", fontsize=13)
    ax.set_xlim(0, max(t) + 2)
    ax.set_ylim(0, 300)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  Saved {save_path}")


def plot_fig10(ts, save_path):
    """Fig 10: Mass flow rate [lbm/s] during pump-down."""
    t = ts["time"]
    mdot_lbm_s = units.kg_s_to_lbm_s(ts["mdot"])
    every = max(1, len(t) // 25)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(t, mdot_lbm_s, "c^-", ms=4, label="Mass Flow Rate", markevery=every)

    t_end = t[-1]
    ax.axvline(t_end, color="red", ls="--", alpha=0.7)
    ax.annotate(
        f"t = {t_end:.0f} s", xy=(t_end, 0.05), fontsize=9, color="red",
        ha="right", xytext=(-5, 5), textcoords="offset points",
    )

    ax.set_xlabel("Time Step [s]", fontsize=12)
    ax.set_ylabel("Refrigerant Mass Flow Rate [lb/s]", fontsize=12)
    ax.set_title("Fig 10: Mass Flow Rate During Pump-Down", fontsize=13)
    ax.set_xlim(0, max(t) + 2)
    ax.set_ylim(0, 0.45)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  Saved {save_path}")
