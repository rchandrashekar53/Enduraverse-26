"""Business-facing battery health rules for EV RUL analytics."""

from __future__ import annotations

import numpy as np
import pandas as pd


def health_classification(capacity_remaining: float, predicted_rul: float) -> str:
    """Classify battery health for maintenance and fleet operations."""
    if capacity_remaining <= 82 or predicted_rul < 500:
        return "Critical"
    if capacity_remaining <= 90 or predicted_rul < 1200:
        return "Moderate"
    return "Healthy"


def maintenance_recommendation(capacity_remaining: float, predicted_rul: float, ood_flag: bool = False) -> str:
    """Return an action-oriented maintenance recommendation."""
    if ood_flag:
        return "Inspect data quality and run manual battery diagnostics."
    if predicted_rul < 300 or capacity_remaining <= 80.5:
        return "Replace soon and trigger preventive maintenance planning."
    if predicted_rul < 500 or capacity_remaining <= 82:
        return "Schedule service inspection within the next maintenance window."
    if predicted_rul < 1200 or capacity_remaining <= 90:
        return "Monitor degradation monthly and review charging behavior."
    return "Battery operating normally; continue standard monitoring."


def warranty_risk_indicator(predicted_rul: float, capacity_remaining: float, confidence_band: str) -> str:
    """Flag warranty exposure level."""
    if predicted_rul < 500 or capacity_remaining <= 82:
        return "High"
    if predicted_rul < 1000 or confidence_band.lower() == "low":
        return "Medium"
    return "Low"


def enrich_business_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Append health, maintenance, and warranty fields to a prediction frame."""
    enriched = df.copy()
    enriched["battery_health_class"] = [
        health_classification(capacity, rul)
        for capacity, rul in zip(enriched["capacity_remaining"], enriched["predicted_rul"])
    ]
    enriched["maintenance_recommendation"] = [
        maintenance_recommendation(capacity, rul, bool(ood))
        for capacity, rul, ood in zip(
            enriched["capacity_remaining"],
            enriched["predicted_rul"],
            enriched.get("is_out_of_distribution", pd.Series(False, index=enriched.index)),
        )
    ]
    enriched["warranty_risk"] = [
        warranty_risk_indicator(rul, capacity, str(conf))
        for rul, capacity, conf in zip(
            enriched["predicted_rul"],
            enriched["capacity_remaining"],
            enriched.get("confidence_band", pd.Series("medium", index=enriched.index)),
        )
    ]
    enriched["replace_soon_flag"] = enriched["predicted_rul"] < 500
    enriched["fleet_priority_score"] = np.clip(
        1000.0 - enriched["predicted_rul"] + (85.0 - enriched["capacity_remaining"]).clip(lower=0) * 12.0,
        0.0,
        None,
    )
    return enriched
