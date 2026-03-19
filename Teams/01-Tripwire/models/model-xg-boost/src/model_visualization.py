"""Plot helpers for evaluation and presentation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def plot_predictions_vs_actual(actual, predicted):
    df = pd.DataFrame({"Actual RUL": actual, "Predicted RUL": predicted})
    fig = px.scatter(df, x="Actual RUL", y="Predicted RUL", title="Actual vs Predicted RUL")
    max_value = float(max(df["Actual RUL"].max(), df["Predicted RUL"].max()))
    fig.add_trace(
        go.Scatter(
            x=[0, max_value],
            y=[0, max_value],
            mode="lines",
            line=dict(color="#2a9d8f", dash="dash"),
            name="Ideal fit",
        )
    )
    fig.update_layout(xaxis_title="Actual RUL", yaxis_title="Predicted RUL")
    return fig


def plot_error_distribution(actual, predicted):
    errors = np.asarray(predicted) - np.asarray(actual)
    fig = px.histogram(
        x=errors,
        nbins=50,
        title="Prediction Error Distribution",
        labels={"x": "Prediction Error (Predicted - Actual)", "y": "Count"},
        color_discrete_sequence=["#f77f00"],
    )
    fig.add_vline(x=0, line_dash="dash", line_color="#003049")
    return fig


def plot_failure_curve(df: pd.DataFrame):
    ordered = df.sort_values("cycle_number")
    fig = go.Figure()
    if "capacity_remaining" in ordered.columns:
        fig.add_trace(
            go.Scatter(
                x=ordered["cycle_number"],
                y=ordered["capacity_remaining"],
                mode="lines",
                name="Capacity Remaining",
                line=dict(color="#2a9d8f", width=3),
            )
        )
        fig.add_hline(y=80, line_dash="dash", line_color="#d62828", annotation_text="80% EOL")
    fig.update_layout(
        title="Failure Prediction Curve",
        xaxis_title="Cycle",
        yaxis_title="Capacity Remaining (%)",
    )
    return fig
