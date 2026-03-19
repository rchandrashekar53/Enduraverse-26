"""Sensitivity analysis for the main degradation stressors."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from src.degradation_model import c_rate_stress_factor, dod_stress_factor, temperature_stress_factor


def conduct_sensitivity_analysis(df: pd.DataFrame | None = None):
    grid = []
    baseline_cycles = 3500.0
    for temperature in [25, 30, 35, 40, 45]:
        for dod in [20, 40, 60, 80]:
            for c_rate in [0.4, 0.8, 1.2, 1.6]:
                combined_stress = (
                    float(temperature_stress_factor(temperature))
                    * float(dod_stress_factor(dod))
                    * float(c_rate_stress_factor(c_rate))
                )
                predicted_life = baseline_cycles / combined_stress
                grid.append(
                    {
                        "temperature": temperature,
                        "dod": dod,
                        "c_rate": c_rate,
                        "predicted_life": max(0.0, min(predicted_life, 4500.0)),
                    }
                )
    sensitivity = pd.DataFrame(grid)
    fig = px.scatter_3d(
        sensitivity,
        x="temperature",
        y="dod",
        z="predicted_life",
        color="c_rate",
        size="predicted_life",
        title="Sensitivity: Temperature vs DoD vs Predicted Life",
    )
    heat = px.density_heatmap(
        sensitivity,
        x="temperature",
        y="dod",
        z="predicted_life",
        color_continuous_scale="Viridis",
        title="Sensitivity Heatmap: Predicted Life",
    )
    return fig, heat


if __name__ == "__main__":
    sensitivity_fig, heat_fig = conduct_sensitivity_analysis()
    sensitivity_fig.write_html("data/sensitivity_3d.html")
    heat_fig.write_html("data/sensitivity_heatmap.html")
    print("Saved sensitivity outputs")
