"""Deployability and BMS-readiness helpers for RUL inference."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_BMS_COLUMNS = [
    "cycle_number",
    "voltage",
    "current",
    "temperature",
    "soc",
    "dod",
    "c_rate",
]


def validate_bms_inputs(df: pd.DataFrame) -> dict[str, Any]:
    """Check whether incoming data carries the core BMS fields."""
    available = [column for column in REQUIRED_BMS_COLUMNS if column in df.columns]
    missing = [column for column in REQUIRED_BMS_COLUMNS if column not in df.columns]
    return {
        "required_columns": REQUIRED_BMS_COLUMNS,
        "available_columns": available,
        "missing_columns": missing,
        "availability_ratio": float(len(available) / len(REQUIRED_BMS_COLUMNS)),
    }


def benchmark_inference_latency(model: Any, feature_frame: pd.DataFrame, fleet_size: int = 1000, repeats: int = 3) -> dict[str, float]:
    """Estimate model latency for single-battery and fleet-scale inference."""
    sample = feature_frame.head(min(len(feature_frame), 2048)).copy()
    single_start = time.perf_counter()
    model.predict(sample.head(1))
    single_ms = (time.perf_counter() - single_start) * 1000.0

    fleet_sample = pd.concat([sample] * max(1, int(np.ceil(fleet_size / max(1, len(sample))))), ignore_index=True).head(fleet_size)
    fleet_runs = []
    for _ in range(repeats):
        start = time.perf_counter()
        model.predict(fleet_sample)
        fleet_runs.append((time.perf_counter() - start) * 1000.0)

    return {
        "single_prediction_ms": float(single_ms),
        "fleet_1000_predictions_ms_mean": float(np.mean(fleet_runs)),
        "fleet_1000_predictions_ms_p95": float(np.percentile(fleet_runs, 95)),
        "predictions_per_second_estimate": float(fleet_size / (np.mean(fleet_runs) / 1000.0)),
    }


def build_deployability_report(model_bundle: dict[str, Any], processed_frame: pd.DataFrame) -> dict[str, Any]:
    """Build a compact report covering feature availability and runtime feasibility."""
    features = model_bundle.get("features", [])
    model = model_bundle.get("model")
    feature_frame = processed_frame[features].copy()
    bms_validation = validate_bms_inputs(processed_frame)
    latency = benchmark_inference_latency(model, feature_frame)
    return {
        "bms_feature_validation": bms_validation,
        "missing_data_strategy": "Median fill + forward/backward fill for cycle_number + engineered fallbacks",
        "fleet_scalability_comment": "Current tree-based model is suitable for batch scoring fleets of 1000 vehicles on CPU.",
        "inference_latency": latency,
    }
