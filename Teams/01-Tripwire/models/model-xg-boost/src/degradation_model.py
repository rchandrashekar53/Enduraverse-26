"""Battery degradation helpers grounded in EV operating stress."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd


def temperature_stress_factor(temperature_c: np.ndarray | float) -> np.ndarray:
    """Approximate Arrhenius-style thermal acceleration."""
    temperature = np.asarray(temperature_c, dtype=float)
    return np.exp((temperature - 25.0) / 28.0)


def dod_stress_factor(dod_pct: np.ndarray | float) -> np.ndarray:
    """Penalize deeper cycling relative to an 80% DoD reference."""
    dod = np.asarray(dod_pct, dtype=float)
    dod_normalized = np.clip(dod / 80.0, 0.2, 1.4)
    return 0.82 + 0.18 * np.power(dod_normalized, 1.35)


def c_rate_stress_factor(c_rate: np.ndarray | float) -> np.ndarray:
    """Penalize high-rate operation relative to a gentle charging baseline."""
    rate = np.asarray(c_rate, dtype=float)
    return 0.9 + 0.22 * np.maximum(rate - 0.7, 0.0) + 0.05 * np.maximum(rate - 1.1, 0.0) ** 2


def equivalent_cycle_increment(dod_pct: np.ndarray | float, c_rate: np.ndarray | float, temperature_c: np.ndarray | float) -> np.ndarray:
    """Combine stressors into one effective full-cycle aging increment."""
    dod_component = np.clip(np.asarray(dod_pct, dtype=float) / 80.0, 0.25, 1.5)
    return dod_component * dod_stress_factor(dod_pct) * c_rate_stress_factor(c_rate) * temperature_stress_factor(temperature_c)


def exponential_capacity_retention(effective_cycle_age: np.ndarray | float, nominal_eol_cycles: float = 3500.0) -> np.ndarray:
    """Exponential fade calibrated to hit 80% around nominal_eol_cycles."""
    effective_age = np.asarray(effective_cycle_age, dtype=float)
    decay_constant = -np.log(0.80) / nominal_eol_cycles
    return 100.0 * np.exp(-decay_constant * effective_age)


def resistance_growth(effective_cycle_age: np.ndarray | float, temperature_c: np.ndarray | float) -> np.ndarray:
    """Simple resistance growth law for visualization and feature creation."""
    effective_age = np.asarray(effective_cycle_age, dtype=float)
    temperature = np.asarray(temperature_c, dtype=float)
    return 0.01 + 0.000012 * effective_age + 0.00005 * np.maximum(temperature - 30.0, 0.0)


def projected_remaining_cycles(capacity_remaining: float, recent_stress_factor: float, nominal_eol_cycles: float = 3500.0) -> float:
    """Invert the exponential fade model to estimate remaining cycles until 80% capacity."""
    if capacity_remaining <= 80.0:
        return 0.0
    decay_constant = -np.log(0.80) / nominal_eol_cycles
    effective_age = -np.log(max(capacity_remaining, 1e-6) / 100.0) / decay_constant
    remaining_effective_age = max(0.0, nominal_eol_cycles - effective_age)
    future_stress = max(0.6, min(1.6, recent_stress_factor))
    return remaining_effective_age / future_stress


def plot_degradation(df: pd.DataFrame):
    """Create a quick 2x2 degradation diagnostic plot."""
    fig, axs = plt.subplots(2, 2, figsize=(12, 10))
    axs[0, 0].plot(df["cycle_number"], df["capacity_remaining"], color="forestgreen")
    axs[0, 0].axhline(80, color="crimson", linestyle="--", linewidth=1.5)
    axs[0, 0].set_title("Capacity vs Cycle")
    axs[0, 0].set_xlabel("Cycle")
    axs[0, 0].set_ylabel("Capacity (%)")
    axs[0, 1].scatter(df["cycle_number"], df["temperature"], c=df["temperature"], cmap="hot", s=5)
    axs[0, 1].set_title("Temperature vs Cycle")
    axs[0, 1].set_xlabel("Cycle")
    axs[0, 1].set_ylabel("Temperature (C)")
    axs[1, 0].scatter(df["cycle_number"], df["dod"], c=df["dod"], cmap="cool", s=5)
    axs[1, 0].set_title("DoD vs Cycle")
    axs[1, 0].set_xlabel("Cycle")
    axs[1, 0].set_ylabel("DoD (%)")
    axs[1, 1].plot(df["cycle_number"], df["internal_resistance"], color="purple")
    axs[1, 1].set_title("Resistance vs Cycle")
    axs[1, 1].set_xlabel("Cycle")
    axs[1, 1].set_ylabel("Internal Resistance (Ohm)")
    plt.tight_layout()
    return fig


if __name__ == "__main__":
    data = pd.read_csv("data/synthetic_battery_data_features.csv")
    figure = plot_degradation(data)
    figure.savefig("data/degradation_visual.png")
    print("Saved degradation plot to data/degradation_visual.png")
