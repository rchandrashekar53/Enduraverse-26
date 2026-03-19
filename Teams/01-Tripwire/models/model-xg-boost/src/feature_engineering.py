"""Feature engineering utilities for degradation-aware RUL models."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.degradation_model import c_rate_stress_factor, dod_stress_factor, temperature_stress_factor


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add physically meaningful degradation features without target leakage."""
    data = df.copy()
    if "voltage" not in data.columns and "avg_voltage" in data.columns:
        data["voltage"] = data["avg_voltage"]
    if "current" not in data.columns and "avg_current" in data.columns:
        data["current"] = data["avg_current"]
    if "c_rate" not in data.columns:
        data["c_rate"] = data.get("avg_current", 0) / 100.0
    if "cycle_number" not in data.columns:
        data["cycle_number"] = np.arange(1, len(data) + 1)

    groups = data.groupby("battery_id", sort=False) if "battery_id" in data.columns else None
    if groups is not None:
        data["rolling_temperature"] = groups["temperature"].transform(lambda series: series.rolling(30, min_periods=1).mean())
        data["avg_dod"] = groups["dod"].transform(lambda series: series.expanding().mean())
        data["max_dod"] = groups["dod"].transform(lambda series: series.expanding().max())
        data["charge_rate_mean"] = groups["c_rate"].transform(lambda series: series.rolling(30, min_periods=1).mean())
    else:
        data["rolling_temperature"] = data["temperature"].rolling(30, min_periods=1).mean()
        data["avg_dod"] = data["dod"].expanding().mean()
        data["max_dod"] = data["dod"].expanding().max()
        data["charge_rate_mean"] = data["c_rate"].rolling(30, min_periods=1).mean()

    data["temperature_stress_factor"] = temperature_stress_factor(data["temperature"])
    data["dod_stress_factor"] = dod_stress_factor(data["dod"])
    data["c_rate_stress_factor"] = c_rate_stress_factor(data["c_rate"])
    data["combined_stress_index"] = (
        data["temperature_stress_factor"] * data["dod_stress_factor"] * data["c_rate_stress_factor"]
    )
    data["equivalent_full_cycles"] = data["cycle_number"] * np.clip(data["dod"] / 100.0, 0.1, 1.0)
    data["temperature_exposure"] = (data["temperature"] > 35).astype(int)
    if groups is not None:
        data["temperature_exposure"] = groups["temperature_exposure"].transform(lambda series: series.cumsum())
    else:
        data["temperature_exposure"] = data["temperature_exposure"].cumsum()
    data["energy_efficiency"] = (data["voltage"] * data["current"].abs()) / (1.0 + data.get("energy_throughput", 0))
    if "capacity_remaining" in data.columns:
        reference_capacity = max(1e-6, float(data["capacity_remaining"].max()))
        data["health_score"] = np.clip(data["capacity_remaining"] / reference_capacity * 100.0, 0, 100)
        data["capacity_fade"] = 100.0 - data["capacity_remaining"]
    else:
        data["health_score"] = 50.0
        data["capacity_fade"] = 0.0
    data["degradation_index"] = (
        data["capacity_fade"] * 0.45
        + data.get("resistance_growth", 0) * 850.0 * 0.2
        + data["combined_stress_index"] * 10.0 * 0.35
    )
    return data


if __name__ == "__main__":
    frame = pd.read_csv("data/synthetic_battery_data.csv")
    engineered = add_features(frame)
    engineered.to_csv("data/synthetic_battery_data_features.csv", index=False)
    print("Feature-engineered dataset saved to data/synthetic_battery_data_features.csv")
