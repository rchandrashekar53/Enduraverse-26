"""Synthetic EV battery dataset generation under MIDC-like operation."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.degradation_model import (
    equivalent_cycle_increment,
    exponential_capacity_retention,
    projected_remaining_cycles,
    resistance_growth,
)
from src.midc_simulation import simulate_midc_drive


def simulate_battery_data(
    n_cycles: int = 4200,
    seed: int = 42,
    temp_scenario: str = "baseline",
    intensity: str = "normal",
) -> pd.DataFrame:
    """Simulate a single eLCV battery pack under MIDC-like daily operation."""
    rng = np.random.default_rng(seed)
    daily_midc_loops = {"low": 12, "normal": 14, "high": 16}.get(intensity, 14)
    base_midc = simulate_midc_drive()
    nominal_eol_cycles = float(rng.integers(3200, 3801))
    stress_cycle_age = 0.0
    calendar_days = 0
    rows: list[dict[str, float]] = []

    for cycle in range(1, int(n_cycles) + 1):
        calendar_days += 1
        ambient_noise = rng.normal(0.0, 1.7)
        if temp_scenario == "hot":
            temperature = np.clip(37 + ambient_noise + 4 * np.sin(cycle / 120), 27, 45)
        elif temp_scenario == "cold":
            temperature = np.clip(22 + ambient_noise + 2 * np.sin(cycle / 150), 15, 32)
        else:
            temperature = np.clip(29 + ambient_noise + 3 * np.sin(cycle / 140), 20, 42)

        loops_today = max(10, daily_midc_loops + int(rng.integers(-1, 2)))
        distance_km = base_midc["distance_km"] * loops_today
        energy_used_kwh = base_midc["energy_kwh"] * loops_today * rng.uniform(0.97, 1.05)
        dod = np.clip((energy_used_kwh / 35.0) * 100.0, 20.0, 85.0)
        avg_current = base_midc["avg_current"] * loops_today * rng.uniform(0.92, 1.08)
        c_rate = np.clip(avg_current / 100.0, 0.25, 1.6)
        voltage = np.clip(base_midc["avg_voltage"] + rng.normal(0.0, 1.8), 342.0, 360.0)
        current = np.clip(avg_current + rng.normal(0.0, 3.0), 20.0, 160.0)
        soc_end = 90.0 - dod
        soc = np.clip((90.0 + max(soc_end, 10.0)) / 2.0 + rng.normal(0.0, 0.7), 12.0, 90.0)

        stress_increment = float(equivalent_cycle_increment(dod, c_rate, temperature))
        stress_cycle_age += stress_increment
        calendar_cycle_penalty = 0.03 * (calendar_days / 365.0)
        effective_age = stress_cycle_age + calendar_cycle_penalty

        capacity_remaining = float(exponential_capacity_retention(effective_age, nominal_eol_cycles))
        capacity_remaining = float(np.clip(capacity_remaining + rng.normal(0.0, 0.05), 70.0, 100.0))
        internal_resistance = float(np.clip(resistance_growth(effective_age, temperature) + rng.normal(0.0, 0.0002), 0.01, 0.08))
        energy_throughput = energy_used_kwh if not rows else rows[-1]["energy_throughput"] + energy_used_kwh
        remaining_cycles = float(projected_remaining_cycles(capacity_remaining, max(stress_increment, 0.75), nominal_eol_cycles))

        rows.append(
            {
                "battery_id": 1,
                "cycle_number": cycle,
                "temperature": temperature,
                "soc": soc,
                "dod": dod,
                "c_rate": c_rate,
                "current": current,
                "voltage": voltage,
                "capacity_remaining": capacity_remaining,
                "internal_resistance": internal_resistance,
                "energy_throughput": energy_throughput,
                "distance_km": distance_km,
                "equivalent_stress_cycles": stress_cycle_age,
                "rul": max(0.0, remaining_cycles),
            }
        )

        if capacity_remaining <= 79.5:
            break

    data = pd.DataFrame(rows)
    data["cycle_age"] = data["cycle_number"]
    data["capacity_fade"] = 100.0 - data["capacity_remaining"]
    data["resistance_growth"] = data["internal_resistance"] - data["internal_resistance"].iloc[0]
    return data


if __name__ == "__main__":
    dataset = simulate_battery_data(4200)
    dataset.to_csv("data/synthetic_battery_data.csv", index=False)
    print("Synthetic battery data written to data/synthetic_battery_data.csv")
