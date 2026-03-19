import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.business_logic import enrich_business_columns
from src.data_loader import load_and_map
from src.evaluation import error_distribution, evaluate_model
from src.model_visualization import plot_error_distribution, plot_failure_curve, plot_predictions_vs_actual
from src.preprocessing import clean_data, create_features, estimate_rul, handle_missing_values

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = PROJECT_ROOT / 'models' / 'rul_model.pkl'
DEFAULT_OUT_PATH = PROJECT_ROOT / 'results' / 'predictions.csv'
DEFAULT_METRICS_PATH = PROJECT_ROOT / 'results' / 'test_metrics.json'
DEFAULT_PLOT_DIR = PROJECT_ROOT / 'results' / 'plots'


def resolve_project_path(path: str | os.PathLike) -> str:
    path_obj = Path(path)
    if path_obj.is_absolute():
        return str(path_obj.resolve())
    if path_obj.exists():
        return str(path_obj.resolve())
    cwd_candidate = Path.cwd() / path_obj
    if path_obj.parts and path_obj.parts[0] == PROJECT_ROOT.name:
        return str(cwd_candidate.resolve())
    path_obj = PROJECT_ROOT / path_obj
    return str(path_obj.resolve())


def prediction_intervals(predictions: np.ndarray, uncertainty_profile: dict):
    if not uncertainty_profile:
        return predictions, predictions
    lower = []
    upper = []
    by_band = uncertainty_profile.get('by_prediction_band', {})
    overall = uncertainty_profile.get('overall', {'lower_residual_q': 0.0, 'upper_residual_q': 0.0})
    for pred in predictions:
        if pred <= 500:
            band = 'near_eol'
        elif pred <= 2000:
            band = 'mid_life'
        else:
            band = 'early_life'
        band_profile = by_band.get(band, overall)
        lower.append(max(0.0, pred + band_profile['lower_residual_q']))
        upper.append(max(0.0, pred + band_profile['upper_residual_q']))
    return np.array(lower), np.array(upper)


def out_of_distribution_flags(df: pd.DataFrame, feature_ranges: dict):
    if not feature_ranges:
        return pd.DataFrame(index=df.index)
    flags = {}
    for feature, stats in feature_ranges.items():
        if feature not in df.columns:
            continue
        lower_margin = stats['min'] - max(1e-9, 0.1 * max(abs(stats['min']), abs(stats['max']), 1.0))
        upper_margin = stats['max'] + max(1e-9, 0.1 * max(abs(stats['min']), abs(stats['max']), 1.0))
        flags[f'{feature}_ood'] = (df[feature] < lower_margin) | (df[feature] > upper_margin)
    return pd.DataFrame(flags, index=df.index)


def confidence_band(width: float):
    if width <= 150:
        return 'high'
    if width <= 350:
        return 'medium'
    return 'low'


def save_evaluation_plots(df: pd.DataFrame, plot_dir: str):
    os.makedirs(plot_dir, exist_ok=True)
    if 'rul' in df.columns:
        plot_predictions_vs_actual(df['rul'], df['predicted_rul']).write_html(str(Path(plot_dir) / 'actual_vs_predicted.html'))
        plot_error_distribution(df['rul'], df['predicted_rul']).write_html(str(Path(plot_dir) / 'error_distribution.html'))
    if 'capacity_remaining' in df.columns and 'cycle_number' in df.columns:
        plot_failure_curve(df).write_html(str(Path(plot_dir) / 'failure_curve.html'))


def predict_single(data_path: str, model_path: str, out_path: str, metrics_out: str, plot_dir: str):
    data_path = resolve_project_path(data_path)
    model_path = resolve_project_path(model_path)
    out_path = resolve_project_path(out_path)
    metrics_out = resolve_project_path(metrics_out)
    plot_dir = resolve_project_path(plot_dir)

    df_raw, mapping, missing = load_and_map(data_path)
    print('Column mapping:', mapping)
    if missing:
        print('Missing columns:', missing)
    df = clean_data(df_raw)
    df = handle_missing_values(df)
    df = create_features(df)
    df = estimate_rul(df)

    loaded = joblib.load(model_path)
    if isinstance(loaded, dict) and 'model' in loaded:
        model = loaded['model']
        features = loaded.get('features', [])
        uncertainty_profile = loaded.get('uncertainty_profile', {})
        feature_ranges = loaded.get('feature_ranges', {})
    else:
        model = loaded
        features = ['cycle_number', 'voltage', 'current', 'temperature', 'soc', 'dod', 'c_rate', 'capacity_remaining', 'internal_resistance', 'energy_throughput', 'cycle_age', 'rolling_temperature', 'avg_dod', 'charge_rate_mean']
        uncertainty_profile = {}
        feature_ranges = {}

    missing_features = [c for c in features if c not in df.columns]
    if missing_features:
        raise ValueError('Prediction dataset is missing required features: ' + ', '.join(missing_features))

    df['predicted_rul'] = np.maximum(0.0, model.predict(df[features]))
    lower_bounds, upper_bounds = prediction_intervals(df['predicted_rul'].to_numpy(), uncertainty_profile)
    df['predicted_rul_lower'] = lower_bounds
    df['predicted_rul_upper'] = upper_bounds
    df['prediction_interval_width'] = df['predicted_rul_upper'] - df['predicted_rul_lower']
    df['confidence_band'] = df['prediction_interval_width'].apply(confidence_band)
    df['predicted_rul_months'] = df['predicted_rul'] / 30.0
    if 'capacity_remaining' in df.columns:
        df['energy_margin_to_eol_kwh'] = np.maximum(0.0, (df['capacity_remaining'] - 80.0) / 100.0 * 35.0)
    else:
        df['energy_margin_to_eol_kwh'] = 0.0

    ood_flags = out_of_distribution_flags(df[features], feature_ranges)
    if not ood_flags.empty:
        df['ood_feature_count'] = ood_flags.sum(axis=1)
        df['is_out_of_distribution'] = df['ood_feature_count'] > 0
    else:
        df['ood_feature_count'] = 0
        df['is_out_of_distribution'] = False

    if 'capacity_remaining' not in df.columns:
        df['capacity_remaining'] = 85.0
    df = enrich_business_columns(df)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    output_columns = [
        col for col in [
            'battery_id',
            'cycle_number',
            'predicted_rul',
            'predicted_rul_lower',
            'predicted_rul_upper',
            'prediction_interval_width',
            'confidence_band',
            'predicted_rul_months',
            'energy_margin_to_eol_kwh',
            'ood_feature_count',
            'is_out_of_distribution',
            'battery_health_class',
            'maintenance_recommendation',
            'warranty_risk',
            'replace_soon_flag',
            'fleet_priority_score',
            'capacity_remaining',
            'rul',
        ] if col in df.columns
    ]
    out = df[output_columns].copy()
    out.to_csv(out_path, index=False)
    print('Predictions saved to', out_path)
    save_evaluation_plots(df, plot_dir)

    metrics = None
    if 'rul' in df.columns:
        metrics = evaluate_model(df['rul'], df['predicted_rul'])
        metrics.update(error_distribution(df['rul'], df['predicted_rul']))
        metrics['interval_coverage'] = float(np.mean((df['rul'] >= df['predicted_rul_lower']) & (df['rul'] <= df['predicted_rul_upper'])))
        metrics['mean_interval_width'] = float(df['prediction_interval_width'].mean())
        metrics['out_of_distribution_rate'] = float(df['is_out_of_distribution'].mean())
        metrics['critical_batteries_share'] = float((df['battery_health_class'] == 'Critical').mean())
        os.makedirs(os.path.dirname(metrics_out), exist_ok=True)
        with open(metrics_out, 'w') as f:
            json.dump(metrics, f, indent=2)
        print('Test metrics saved to', metrics_out)
        print('Test Metrics:')
        print(f"  RMSE: {metrics['RMSE']:.4f}")
        print(f"  MAE: {metrics['MAE']:.4f}")
        print(f"  R2: {metrics['R2']:.4f}")
    else:
        print('No true RUL column available for test metrics.')

    return out, metrics


def predict_batch_directory(batch_dir: str, model_path: str, out_dir: str):
    batch_path = Path(resolve_project_path(batch_dir))
    output_dir = Path(resolve_project_path(out_dir))
    if output_dir.suffix:
        output_dir = output_dir.parent / output_dir.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for csv_path in sorted(batch_path.glob('*.csv')):
        output_csv = output_dir / f'{csv_path.stem}_predictions.csv'
        metrics_json = output_dir / f'{csv_path.stem}_metrics.json'
        plot_dir = output_dir / f'{csv_path.stem}_plots'
        _, metrics = predict_single(str(csv_path), model_path, str(output_csv), str(metrics_json), str(plot_dir))
        summary_row = {'dataset': csv_path.name}
        if metrics:
            summary_row.update(metrics)
        summary_rows.append(summary_row)
    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df.to_csv(output_dir / 'batch_summary.csv', index=False)
        print('Batch summary saved to', output_dir / 'batch_summary.csv')
    return summary_df


def main():
    parser = argparse.ArgumentParser(description='Predict RUL from CSV')
    parser.add_argument('--data', default=None, help='Path to CSV file')
    parser.add_argument('--batch-dir', default=None, help='Optional directory of CSV files for batch scoring')
    parser.add_argument('--model', default=str(DEFAULT_MODEL_PATH), help='Trained model path')
    parser.add_argument('--out', default=str(DEFAULT_OUT_PATH), help='Output CSV path')
    parser.add_argument('--metrics', default=str(DEFAULT_METRICS_PATH), help='Output metrics JSON path')
    parser.add_argument('--plot-dir', default=str(DEFAULT_PLOT_DIR), help='Directory for evaluation plots')
    args = parser.parse_args()
    if args.batch_dir:
        predict_batch_directory(args.batch_dir, args.model, args.out)
    elif args.data:
        predict_single(args.data, args.model, args.out, args.metrics, args.plot_dir)
    else:
        raise ValueError('Provide either --data or --batch-dir')


if __name__ == '__main__':
    main()
