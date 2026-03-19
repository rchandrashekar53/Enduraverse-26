"""Compatibility helpers for training and inference within the src package."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from train_model import MODEL_FEATURES, grouped_validation_metrics, make_models
from src.preprocessing import create_features, estimate_rul, handle_missing_values


def train_rul_model(df: pd.DataFrame, save_path: str = "models/rul_model.pkl"):
    """Train a model from an in-memory frame using the project-standard pipeline."""
    data = handle_missing_values(create_features(df.copy()))
    data = estimate_rul(data)
    if "battery_id" not in data.columns:
        data["battery_id"] = 1
    features = [feature for feature in MODEL_FEATURES if feature in data.columns]
    data = data.dropna(subset=features + ["rul"]).copy()

    validation_results = grouped_validation_metrics(data, features, make_models())
    best_name = min(validation_results, key=lambda name: validation_results[name]["mean_RMSE"])
    model = make_models()[best_name]
    model.fit(data[features], data["rul"])
    bundle = {"model": model, "model_name": best_name, "features": features}
    joblib.dump(bundle, save_path)
    return bundle, validation_results


def predict_rul(model_bundle, df: pd.DataFrame):
    """Predict RUL from a trained bundle or bare model object."""
    prepared = handle_missing_values(create_features(df.copy()))
    if isinstance(model_bundle, dict) and "model" in model_bundle:
        model = model_bundle["model"]
        features = model_bundle.get("features", [])
    else:
        model = model_bundle
        features = [feature for feature in MODEL_FEATURES if feature in prepared.columns]
    return np.maximum(0.0, model.predict(prepared[features]))


if __name__ == "__main__":
    sample_path = Path("data") / "synthetic_battery_data_features.csv"
    frame = pd.read_csv(sample_path)
    bundle, metrics = train_rul_model(frame)
    print("Best model:", bundle["model_name"])
    print("Validation metrics:", metrics[bundle["model_name"]])
