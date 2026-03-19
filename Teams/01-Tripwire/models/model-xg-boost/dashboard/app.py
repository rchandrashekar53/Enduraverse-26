import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.business_logic import enrich_business_columns
from src.model_visualization import plot_failure_curve
from src.preprocessing import clean_data, handle_missing_values, create_features, estimate_rul
from src.sensitivity_analysis import conduct_sensitivity_analysis

MODEL_PATH = ROOT / "models" / "rul_model.pkl"
METRICS_PATH = ROOT / "models" / "training_metrics.json"
PREDICTIONS_PATH = ROOT / "results" / "predictions.csv"
DEFAULT_DATA_PATH = ROOT / "data" / "battery_set_clean_test_20.csv"


def load_json(path: Path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_model_bundle():
    if not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


def prediction_intervals(predictions: np.ndarray, uncertainty_profile: dict):
    if not uncertainty_profile:
        return predictions, predictions
    overall = uncertainty_profile.get("overall", {"lower_residual_q": 0.0, "upper_residual_q": 0.0})
    by_band = uncertainty_profile.get("by_prediction_band", {})
    lower = []
    upper = []
    for prediction in predictions:
        if prediction <= 500:
            band = "near_eol"
        elif prediction <= 2000:
            band = "mid_life"
        else:
            band = "early_life"
        band_profile = by_band.get(band, overall)
        lower.append(max(0.0, prediction + band_profile["lower_residual_q"]))
        upper.append(max(0.0, prediction + band_profile["upper_residual_q"]))
    return np.array(lower), np.array(upper)


def confidence_band(width: float):
    if width <= 150:
        return "High"
    if width <= 350:
        return "Medium"
    return "Low"


def out_of_distribution_flags(df: pd.DataFrame, feature_ranges: dict):
    flags = pd.DataFrame(index=df.index)
    for feature, stats in feature_ranges.items():
        if feature not in df.columns:
            continue
        margin = max(1e-9, 0.1 * max(abs(stats["min"]), abs(stats["max"]), 1.0))
        lower = stats["min"] - margin
        upper = stats["max"] + margin
        flags[f"{feature}_ood"] = (df[feature] < lower) | (df[feature] > upper)
    return flags


def score_uploaded_dataset(df_raw: pd.DataFrame, model_bundle: dict):
    mapped_df, mapping, missing = load_and_map_from_frame(df_raw)
    df = clean_data(mapped_df)
    df = handle_missing_values(df)
    df = create_features(df)
    df = estimate_rul(df)

    model = model_bundle["model"]
    features = model_bundle.get("features", [])
    missing_features = [feature for feature in features if feature not in df.columns]
    if missing_features:
        raise ValueError("Uploaded dataset is missing required engineered features: " + ", ".join(missing_features))

    predictions = np.maximum(0.0, model.predict(df[features]))
    lower, upper = prediction_intervals(predictions, model_bundle.get("uncertainty_profile", {}))
    df["predicted_rul"] = predictions
    df["predicted_rul_lower"] = lower
    df["predicted_rul_upper"] = upper
    df["prediction_interval_width"] = upper - lower
    df["confidence_band"] = df["prediction_interval_width"].apply(confidence_band)
    df["predicted_rul_months"] = df["predicted_rul"] / 30.0
    if "capacity_remaining" in df.columns:
        df["energy_margin_to_eol_kwh"] = np.maximum(0.0, (df["capacity_remaining"] - 80.0) / 100.0 * 35.0)
    else:
        df["energy_margin_to_eol_kwh"] = 0.0
    flags = out_of_distribution_flags(df[features], model_bundle.get("feature_ranges", {}))
    if not flags.empty:
        df["ood_feature_count"] = flags.sum(axis=1)
        df["is_out_of_distribution"] = df["ood_feature_count"] > 0
    else:
        df["ood_feature_count"] = 0
        df["is_out_of_distribution"] = False

    if "capacity_remaining" not in df.columns:
        df["capacity_remaining"] = 85.0
    df = enrich_business_columns(df)

    return df, mapping, missing


def load_and_map_from_frame(df: pd.DataFrame):
    from src.data_loader import map_columns

    return map_columns(df)


def load_default_dataset():
    if DEFAULT_DATA_PATH.exists():
        return pd.read_csv(DEFAULT_DATA_PATH)
    return pd.DataFrame()


def load_predictions_frame():
    if PREDICTIONS_PATH.exists():
        return pd.read_csv(PREDICTIONS_PATH)
    return pd.DataFrame()


def latest_snapshot(predictions: pd.DataFrame):
    if predictions.empty:
        return pd.DataFrame()
    snapshot = predictions.sort_values("cycle_number").groupby("battery_id", as_index=False).tail(1)
    return snapshot.sort_values("predicted_rul")


def status_label(rul_value: float):
    if rul_value < 300:
        return "Immediate attention"
    if rul_value < 800:
        return "Watchlist"
    return "Stable"


def hero_metric(label: str, value: str, caption: str):
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-label">{label}</div>
            <div class="hero-value">{value}</div>
            <div class="hero-caption">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def make_line_theme(fig: go.Figure):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.88)",
        font=dict(family="Georgia", color="#14213d"),
        margin=dict(l=20, r=20, t=50, b=20),
        title=dict(font=dict(size=22)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(20,33,61,0.08)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(20,33,61,0.08)")
    return fig


def chart_rul_band(battery_df: pd.DataFrame, selected_row: pd.Series | None = None):
    ordered = battery_df.sort_values("cycle_number")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=ordered["cycle_number"],
            y=ordered["predicted_rul_upper"],
            mode="lines",
            line=dict(color="rgba(47,79,79,0)"),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ordered["cycle_number"],
            y=ordered["predicted_rul_lower"],
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(242, 153, 74, 0.22)",
            line=dict(color="rgba(47,79,79,0)"),
            name="Prediction interval",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ordered["cycle_number"],
            y=ordered["predicted_rul"],
            mode="lines",
            line=dict(color="#f77f00", width=3),
            name="Predicted RUL",
        )
    )
    if "rul" in ordered.columns:
        fig.add_trace(
            go.Scatter(
                x=ordered["cycle_number"],
                y=ordered["rul"],
                mode="lines",
                line=dict(color="#003049", width=2, dash="dot"),
                name="Actual RUL",
            )
        )
    if selected_row is not None:
        fig.add_trace(
            go.Scatter(
                x=[selected_row["cycle_number"]],
                y=[selected_row["predicted_rul"]],
                mode="markers",
                marker=dict(size=12, color="#d62828", line=dict(width=2, color="#fffaf1")),
                name="Selected cycle",
            )
        )
    fig.update_layout(title="RUL Forecast With Confidence Envelope", xaxis_title="Cycle", yaxis_title="Remaining Useful Life")
    return make_line_theme(fig)


def chart_actual_vs_predicted(predictions: pd.DataFrame):
    scatter = px.scatter(
        predictions.sample(min(len(predictions), 7000), random_state=42),
        x="rul",
        y="predicted_rul",
        color="prediction_interval_width",
        color_continuous_scale=["#003049", "#f77f00", "#fcbf49"],
        opacity=0.55,
        title="Actual vs Predicted RUL",
        labels={"rul": "Actual RUL", "predicted_rul": "Predicted RUL", "prediction_interval_width": "Interval Width"},
    )
    max_value = max(predictions["rul"].max(), predictions["predicted_rul"].max())
    scatter.add_trace(
        go.Scatter(
            x=[0, max_value],
            y=[0, max_value],
            mode="lines",
            line=dict(color="#2a9d8f", dash="dash"),
            name="Ideal fit",
        )
    )
    return make_line_theme(scatter)


def chart_battery_leaderboard(snapshot: pd.DataFrame):
    ranked = snapshot.nsmallest(12, "predicted_rul").copy()
    ranked["status"] = ranked["predicted_rul"].apply(status_label)
    fig = px.bar(
        ranked,
        x="predicted_rul",
        y=ranked["battery_id"].astype(str),
        color="status",
        orientation="h",
        title="Fleet Attention Board",
        color_discrete_map={
            "Immediate attention": "#d62828",
            "Watchlist": "#f77f00",
            "Stable": "#2a9d8f",
        },
        labels={"x": "Predicted RUL", "y": "Battery ID"},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return make_line_theme(fig)


def chart_capacity_vs_rul(predictions: pd.DataFrame):
    sample = predictions.sample(min(len(predictions), 6000), random_state=42)
    fig = px.scatter(
        sample,
        x="capacity_remaining",
        y="predicted_rul",
        color="confidence_band",
        title="Capacity Remaining vs Predicted RUL",
        color_discrete_map={"High": "#2a9d8f", "Medium": "#f77f00", "Low": "#d62828"},
        labels={"capacity_remaining": "Capacity Remaining (%)", "predicted_rul": "Predicted RUL"},
    )
    return make_line_theme(fig)


def chart_lifecycle_metrics(metrics_payload: dict):
    rows = []
    for phase, values in metrics_payload.get("test_lifecycle_metrics", {}).items():
        rows.append(
            {
                "Lifecycle Stage": phase.replace("_", " ").title(),
                "RMSE": values["RMSE"],
                "MAE": values["MAE"],
                "R2": values["R2"],
            }
        )
    lifecycle_df = pd.DataFrame(rows)
    fig = px.bar(
        lifecycle_df,
        x="Lifecycle Stage",
        y="RMSE",
        color="Lifecycle Stage",
        title="Error Profile Across Battery Lifecycle",
        color_discrete_sequence=["#003049", "#f77f00", "#d62828"],
    )
    return make_line_theme(fig)


def chart_validation_comparison(metrics_payload: dict):
    rows = []
    for name, values in metrics_payload.get("grouped_validation", {}).items():
        rows.append(
            {
                "Model": name.upper(),
                "RMSE": values["mean_RMSE"],
                "MAE": values["mean_MAE"],
                "R2": values["mean_R2"],
            }
        )
    comparison_df = pd.DataFrame(rows)
    fig = px.bar(
        comparison_df,
        x="Model",
        y=["RMSE", "MAE"],
        barmode="group",
        title="Grouped Validation Model Comparison",
        color_discrete_sequence=["#f77f00", "#003049"],
    )
    return make_line_theme(fig)


def chart_feature_importance(model_bundle: dict):
    if not model_bundle:
        return go.Figure()
    model = model_bundle.get("model")
    features = model_bundle.get("features", [])
    if not hasattr(model, "feature_importances_"):
        return go.Figure()
    importance_df = pd.DataFrame(
        {"Feature": features, "Importance": model.feature_importances_}
    ).sort_values("Importance", ascending=False).head(12)
    fig = px.bar(
        importance_df.sort_values("Importance"),
        x="Importance",
        y="Feature",
        orientation="h",
        title="Top Model Drivers",
        color="Importance",
        color_continuous_scale=["#003049", "#f77f00", "#fcbf49"],
    )
    return make_line_theme(fig)


def chart_driver_groups(metrics_payload: dict):
    groups = metrics_payload.get("driver_importance_groups", {})
    if not groups:
        return go.Figure()
    group_df = pd.DataFrame(
        {"Driver Group": [name.replace("_", " ").title() for name in groups], "Importance": list(groups.values())}
    ).sort_values("Importance")
    fig = px.bar(
        group_df,
        x="Importance",
        y="Driver Group",
        orientation="h",
        title="Grouped Degradation Drivers",
        color="Importance",
        color_continuous_scale=["#003049", "#f77f00", "#fcbf49"],
    )
    return make_line_theme(fig)


def inject_styles():
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(252,191,73,0.22), transparent 28%),
                radial-gradient(circle at top right, rgba(42,157,143,0.18), transparent 26%),
                linear-gradient(180deg, #fffaf1 0%, #f5f1e8 45%, #eef3f6 100%);
            color: #14213d;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1320px;
        }
        h1, h2, h3 {
            font-family: Georgia, "Times New Roman", serif !important;
            color: #0f172a;
            letter-spacing: -0.02em;
        }
        .hero-shell {
            background: linear-gradient(135deg, rgba(0,48,73,0.96), rgba(20,33,61,0.92));
            border-radius: 26px;
            padding: 28px 30px;
            box-shadow: 0 20px 60px rgba(20, 33, 61, 0.18);
            margin-bottom: 1.2rem;
            color: #fdfaf3;
        }
        .hero-kicker {
            font-size: 0.78rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: #fcbf49;
            margin-bottom: 0.4rem;
            font-weight: 700;
        }
        .hero-title {
            font-size: 2.4rem;
            font-weight: 700;
            line-height: 1.05;
            margin-bottom: 0.4rem;
        }
        .hero-subtitle {
            max-width: 760px;
            color: rgba(255,255,255,0.78);
            font-size: 1rem;
        }
        .hero-card {
            background: rgba(255,255,255,0.82);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.55);
            border-radius: 22px;
            padding: 18px 18px 16px 18px;
            box-shadow: 0 14px 34px rgba(20,33,61,0.08);
            min-height: 132px;
        }
        .hero-label {
            color: #5f6c7b;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.6rem;
        }
        .hero-value {
            color: #0f172a;
            font-size: 2rem;
            line-height: 1;
            font-weight: 800;
            margin-bottom: 0.55rem;
        }
        .hero-caption {
            color: #5f6c7b;
            font-size: 0.95rem;
        }
        .section-shell {
            background: rgba(255,255,255,0.72);
            border: 1px solid rgba(255,255,255,0.65);
            border-radius: 24px;
            padding: 16px 18px 18px 18px;
            box-shadow: 0 10px 28px rgba(20,33,61,0.06);
            margin-bottom: 1rem;
        }
        .mini-note {
            color: #54606f;
            font-size: 0.92rem;
            margin-top: -0.35rem;
            margin-bottom: 0.8rem;
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,0.7);
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,0.55);
            padding: 12px 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(page_title="Battery RUL Command Center", page_icon=":battery:", layout="wide")
    inject_styles()

    metrics_payload = load_json(METRICS_PATH)
    model_bundle = load_model_bundle()
    saved_predictions = load_predictions_frame()

    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-kicker">Battery Intelligence Studio</div>
            <div class="hero-title">Production-Ready Battery RUL Presentation Dashboard</div>
            <div class="hero-subtitle">
                Live-ready command center for remaining useful life forecasting, fleet risk triage,
                confidence monitoring, and model credibility storytelling.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Control Panel")
        mode = st.radio("Dataset mode", ["Saved demo outputs", "Upload custom CSV"], index=0)
        uploaded_file = st.file_uploader("Upload battery CSV", type=["csv"])
        st.caption("Tip: use the saved outputs during the presentation for the smoothest experience.")

    mapping = {}
    missing = []
    if mode == "Upload custom CSV" and uploaded_file is not None and model_bundle is not None:
        raw_df = pd.read_csv(uploaded_file)
        predictions = None
        try:
            predictions, mapping, missing = score_uploaded_dataset(raw_df, model_bundle)
        except Exception as exc:
            st.error(f"Could not score uploaded dataset: {exc}")
            predictions = pd.DataFrame()
    else:
        predictions = saved_predictions.copy()

    if predictions.empty:
        st.warning("No predictions available yet. Run training and prediction first, or upload a valid dataset.")
        return

    if "battery_id" not in predictions.columns:
        predictions["battery_id"] = "Demo"
    if "battery_health_class" not in predictions.columns and "capacity_remaining" in predictions.columns:
        predictions = enrich_business_columns(predictions)

    snapshot = latest_snapshot(predictions)
    selected_battery = st.sidebar.selectbox(
        "Battery spotlight",
        snapshot["battery_id"].astype(str).tolist(),
        index=0,
    )
    selected_battery_int = int(selected_battery) if str(selected_battery).isdigit() else selected_battery
    battery_df = predictions[predictions["battery_id"] == selected_battery_int].copy()
    battery_df = battery_df.sort_values("cycle_number")
    cycle_min = int(battery_df["cycle_number"].min())
    cycle_max = int(battery_df["cycle_number"].max())
    selected_cycle = st.sidebar.slider("Cycle spotlight", min_value=cycle_min, max_value=cycle_max, value=cycle_max)
    selected_row_df = battery_df.loc[battery_df["cycle_number"] == selected_cycle]
    if selected_row_df.empty:
        selected_row = battery_df.iloc[-1]
    else:
        selected_row = selected_row_df.iloc[-1]

    rmse = metrics_payload.get("test_metrics", {}).get("RMSE", np.nan)
    r2 = metrics_payload.get("test_metrics", {}).get("R2", np.nan)
    coverage = metrics_payload.get("test_interval_metrics", {}).get("coverage", np.nan)
    baseline_rmse = metrics_payload.get("baseline_test_metrics", {}).get("RMSE", np.nan)
    improvement = ((baseline_rmse - rmse) / baseline_rmse * 100.0) if baseline_rmse and not np.isnan(rmse) else np.nan

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        hero_metric("Battery Spotlight", f"{selected_battery}", f"{status_label(selected_row['predicted_rul'])}")
    with c2:
        hero_metric("Selected Cycle RUL", f"{selected_row['predicted_rul']:.0f}", f"Cycle {int(selected_row['cycle_number'])} | {selected_row['confidence_band']} confidence")
    with c3:
        hero_metric("Test RMSE", f"{rmse:.1f}", f"{improvement:.1f}% better than baseline")
    with c4:
        hero_metric("Interval Coverage", f"{coverage * 100:.1f}%", f"Test R2 = {r2:.3f}")

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    left, right = st.columns([1.8, 1.2])
    with left:
        st.plotly_chart(chart_rul_band(battery_df, selected_row=selected_row), use_container_width=True)
    with right:
        st.subheader("Battery Storyline")
        st.markdown(
            f"""
            <div class="mini-note">
            At <b>cycle {int(selected_row['cycle_number'])}</b>, battery <b>{selected_battery}</b> projects
            <b>{selected_row['predicted_rul']:.0f}</b> remaining cycles.
            The forecast interval ranges from <b>{selected_row['predicted_rul_lower']:.0f}</b> to <b>{selected_row['predicted_rul_upper']:.0f}</b> cycles.
            </div>
            """,
            unsafe_allow_html=True,
        )
        metric_cols = st.columns(2)
        metric_cols[0].metric("Capacity Remaining", f"{selected_row['capacity_remaining']:.2f}%")
        metric_cols[1].metric("OOD Flags", int(selected_row.get("ood_feature_count", 0)))
        metric_cols = st.columns(2)
        metric_cols[0].metric("Estimated Months Left", f"{selected_row.get('predicted_rul_months', selected_row['predicted_rul'] / 30.0):.1f}")
        metric_cols[1].metric("Energy To EOL", f"{selected_row.get('energy_margin_to_eol_kwh', 0.0):.2f} kWh")
        metric_cols = st.columns(2)
        metric_cols[0].metric("Health Class", str(selected_row.get("battery_health_class", "n/a")))
        metric_cols[1].metric("Warranty Risk", str(selected_row.get("warranty_risk", "n/a")))
        if "rul" in selected_row.index:
            metric_cols = st.columns(2)
            metric_cols[0].metric("Actual RUL", f"{selected_row['rul']:.0f}")
            metric_cols[1].metric("Prediction Error", f"{abs(selected_row['predicted_rul'] - selected_row['rul']):.0f}")
        st.info(str(selected_row.get("maintenance_recommendation", "No maintenance note available.")))
        st.dataframe(
            snapshot[["battery_id", "predicted_rul", "predicted_rul_lower", "predicted_rul_upper", "capacity_remaining", "battery_health_class", "warranty_risk"]]
            .rename(
                columns={
                    "battery_id": "Battery",
                    "predicted_rul": "Predicted RUL",
                    "predicted_rul_lower": "Lower",
                    "predicted_rul_upper": "Upper",
                    "capacity_remaining": "Capacity %",
                    "battery_health_class": "Health",
                    "warranty_risk": "Warranty Risk",
                }
            )
            .head(8),
            use_container_width=True,
            hide_index=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.subheader("Battery & Cycle Detail Explorer")
    st.caption("Use this during the presentation to answer questions about any battery at any cycle.")
    explorer_df = battery_df.reset_index(drop=True)
    table_left, table_right = st.columns([1.1, 2.2])
    with table_left:
        st.metric("Selected Battery", str(selected_battery))
        st.metric("Selected Cycle", int(selected_row["cycle_number"]))
    with table_right:
        window = st.slider("Neighboring rows to show", min_value=0, max_value=25, value=3)
    cycle_detail = explorer_df.loc[explorer_df["cycle_number"] == selected_cycle]
    if cycle_detail.empty:
        cycle_detail = explorer_df.iloc[[-1]]
    center_idx = int(cycle_detail.index[0])
    nearby_rows = explorer_df.iloc[max(0, center_idx - window): min(len(explorer_df), center_idx + window + 1)]
    st.dataframe(cycle_detail.T.rename(columns={cycle_detail.index[0]: "Selected Value"}), use_container_width=True)
    st.caption("Nearby context around the selected cycle")
    st.dataframe(nearby_rows, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    row_a, row_b = st.columns(2)
    with row_a:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.plotly_chart(chart_actual_vs_predicted(predictions), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with row_b:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.plotly_chart(chart_battery_leaderboard(snapshot), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    row_c, row_d = st.columns(2)
    with row_c:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.plotly_chart(chart_validation_comparison(metrics_payload), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with row_d:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.plotly_chart(chart_lifecycle_metrics(metrics_payload), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.plotly_chart(plot_failure_curve(battery_df), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.plotly_chart(chart_feature_importance(model_bundle), use_container_width=True)
    st.caption("Explainability view: temperature, DoD, and C-rate derived features should appear among the top degradation drivers.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.plotly_chart(chart_driver_groups(metrics_payload), use_container_width=True)
    st.caption("Judge-facing summary of the main degradation themes affecting RUL.")
    st.markdown("</div>", unsafe_allow_html=True)

    row_e, row_f = st.columns([1.25, 1.0])
    with row_e:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.plotly_chart(chart_capacity_vs_rul(predictions), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with row_f:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.subheader("Model Credibility")
        st.caption("A compact presentation slide built into the app.")
        overview = pd.DataFrame(
            [
                ["Best Model", metrics_payload.get("best_model", "n/a").upper()],
                ["Grouped Validation RMSE", f"{metrics_payload.get('best_rmse', np.nan):.2f}"],
                ["Final Test RMSE", f"{metrics_payload.get('test_metrics', {}).get('RMSE', np.nan):.2f}"],
                ["Final Test MAE", f"{metrics_payload.get('test_metrics', {}).get('MAE', np.nan):.2f}"],
                ["Final Test R2", f"{metrics_payload.get('test_metrics', {}).get('R2', np.nan):.4f}"],
                ["Interval Coverage", f"{metrics_payload.get('test_interval_metrics', {}).get('coverage', np.nan) * 100:.2f}%"],
                ["Mean Interval Width", f"{metrics_payload.get('test_interval_metrics', {}).get('mean_interval_width', np.nan):.2f}"],
                ["Baseline RMSE", f"{metrics_payload.get('baseline_test_metrics', {}).get('RMSE', np.nan):.2f}"],
            ],
            columns=["Metric", "Value"],
        )
        st.dataframe(overview, use_container_width=True, hide_index=True)
        if mapping:
            st.write("Upload column mapping")
            st.json(mapping)
        if missing:
            st.warning("Missing uploaded columns: " + ", ".join(missing))
        st.markdown(
            """
            **Talk track**

            - Grouped battery validation was used to avoid optimistic row leakage.
            - The final test set stayed untouched until the end.
            - Every forecast now ships with a confidence interval and OOD safety signal.
            """
        )
        st.markdown("</div>", unsafe_allow_html=True)

    sens_fig, heat_fig = conduct_sensitivity_analysis(pd.DataFrame())
    sens_left, sens_right = st.columns(2)
    with sens_left:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.plotly_chart(sens_fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with sens_right:
        st.markdown('<div class="section-shell">', unsafe_allow_html=True)
        st.plotly_chart(heat_fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-shell">', unsafe_allow_html=True)
    st.subheader("Fleet Snapshot")
    leaderboard = snapshot.copy()
    leaderboard["Status"] = leaderboard["predicted_rul"].apply(status_label)
    leaderboard["Confidence"] = leaderboard["confidence_band"]
    leaderboard["Predicted RUL"] = leaderboard["predicted_rul"].round(1)
    leaderboard["Lower"] = leaderboard["predicted_rul_lower"].round(1)
    leaderboard["Upper"] = leaderboard["predicted_rul_upper"].round(1)
    leaderboard["Capacity %"] = leaderboard["capacity_remaining"].round(2)
    if "battery_health_class" in leaderboard.columns:
        leaderboard["Health"] = leaderboard["battery_health_class"]
    if "warranty_risk" in leaderboard.columns:
        leaderboard["Warranty Risk"] = leaderboard["warranty_risk"]
    if "maintenance_recommendation" in leaderboard.columns:
        leaderboard["Maintenance Recommendation"] = leaderboard["maintenance_recommendation"]
    st.dataframe(
        leaderboard[[col for col in ["battery_id", "Predicted RUL", "Lower", "Upper", "Capacity %", "Confidence", "Health", "Warranty Risk", "Status", "Maintenance Recommendation"] if col in leaderboard.columns]]
        .rename(columns={"battery_id": "Battery"}),
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()

