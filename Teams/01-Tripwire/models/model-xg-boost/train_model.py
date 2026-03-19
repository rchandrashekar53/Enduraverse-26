import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBRegressor

from src.deployability import build_deployability_report
from src.data_loader import load_and_map
from src.evaluation import error_distribution, evaluate_model
from src.preprocessing import clean_data, create_features, estimate_rul, handle_missing_values

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_TRAIN_DATA = PROJECT_ROOT / 'data' / 'battery_set_clean_train_80.csv'
DEFAULT_TEST_DATA = PROJECT_ROOT / 'data' / 'battery_set_clean_test_20.csv'
DEFAULT_MODEL_PATH = PROJECT_ROOT / 'models' / 'rul_model.pkl'
DEFAULT_METRICS_PATH = PROJECT_ROOT / 'models' / 'training_metrics.json'
DEFAULT_DEPLOYABILITY_PATH = PROJECT_ROOT / 'models' / 'deployability_report.json'
VALIDATION_SPLITS = 3
VALIDATION_TEST_SIZE = 0.2
FINAL_TRAIN_SAMPLE_SIZE = 250000

MODEL_FEATURES = [
    'cycle_number',
    'voltage',
    'current',
    'current_abs',
    'temperature',
    'soc',
    'dod',
    'c_rate',
    'capacity_remaining',
    'internal_resistance',
    'energy_throughput',
    'cycle_age',
    'rolling_temperature',
    'avg_dod',
    'charge_rate_mean',
    'rolling_voltage_avg',
    'capacity_fade',
    'capacity_fade_rate',
    'thermal_stress_index',
    'health_score',
    'power_draw',
    'temperature_soc_interaction',
    'voltage_drop_from_avg',
    'temperature_stress_factor',
    'dod_stress_factor',
    'c_rate_stress_factor',
    'equivalent_full_cycles',
    'combined_stress_index',
    'capacity_margin_to_eol',
    'degradation_rate_est',
    'physics_rul_proxy',
    'remaining_calendar_months_proxy',
]


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


def prepare_data(data_path: str):
    data_path = resolve_project_path(data_path)
    df_raw, mapping, missing = load_and_map(data_path)
    print('Column mapping:', mapping)
    if missing:
        print('Missing columns:', missing)
    df = clean_data(df_raw)
    df = handle_missing_values(df)
    df = create_features(df)
    df = estimate_rul(df)
    required = ['cycle_number', 'voltage', 'current', 'temperature', 'soc', 'dod', 'c_rate', 'capacity_remaining', 'rul']
    for col in required:
        if col not in df.columns:
            raise ValueError(f'Missing required column after preprocessing: {col}')
    features = [feature for feature in MODEL_FEATURES if feature in df.columns]
    data = df.dropna(subset=features + ['rul']).copy()
    return data, features


def make_models():
    return {
        'rf': RandomForestRegressor(
            n_estimators=120,
            max_depth=16,
            min_samples_leaf=2,
            max_features='sqrt',
            bootstrap=True,
            random_state=42,
            n_jobs=1,
        ),
        'xgb': XGBRegressor(
            n_estimators=160,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            min_child_weight=2,
            tree_method='hist',
            objective='reg:squarederror',
            random_state=42,
            n_jobs=1,
        ),
    }


def maybe_downsample_rows(data: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    if len(data) <= max_rows:
        return data
    sampled_groups = []
    for _, group in data.groupby('battery_id', sort=False):
        if len(group) <= 1:
            sampled_groups.append(group)
            continue
        fraction = max_rows / len(data)
        keep = max(1, int(len(group) * fraction))
        sampled_groups.append(group.sample(n=min(len(group), keep), random_state=42))
    sampled = pd.concat(sampled_groups).sort_index()
    if len(sampled) > max_rows:
        sampled = sampled.sample(n=max_rows, random_state=42).sort_index()
    return sampled


def grouped_validation_metrics(data: pd.DataFrame, features: list[str], models: dict):
    splitter = GroupShuffleSplit(
        n_splits=VALIDATION_SPLITS,
        test_size=VALIDATION_TEST_SIZE,
        random_state=42,
    )
    groups = data['battery_id'] if 'battery_id' in data.columns else data['cycle_number']
    validation_results = {}

    for model_name, model_factory in models.items():
        split_metrics = []
        oof_frames = []
        for split_index, (train_idx, val_idx) in enumerate(splitter.split(data[features], data['rul'], groups=groups), start=1):
            split_train = data.iloc[train_idx]
            split_val = data.iloc[val_idx]
            candidate = model_factory
            candidate.fit(split_train[features], split_train['rul'])
            predictions = np.maximum(0.0, candidate.predict(split_val[features]))
            metrics = evaluate_model(split_val['rul'], predictions)
            metrics['split'] = split_index
            split_metrics.append(metrics)
            oof_frames.append(pd.DataFrame({
                'actual_rul': split_val['rul'].to_numpy(),
                'predicted_rul': predictions,
            }))

        oof_df = pd.concat(oof_frames, ignore_index=True)
        validation_results[model_name] = {
            'mean_RMSE': float(np.mean([m['RMSE'] for m in split_metrics])),
            'mean_MAE': float(np.mean([m['MAE'] for m in split_metrics])),
            'mean_R2': float(np.mean([m['R2'] for m in split_metrics])),
            'splits': split_metrics,
            'uncertainty_profile': build_uncertainty_profile(oof_df['actual_rul'], oof_df['predicted_rul']),
        }

    return validation_results


def fit_final_model(model_name: str, data: pd.DataFrame, features: list[str]):
    final_training_data = maybe_downsample_rows(data, FINAL_TRAIN_SAMPLE_SIZE)
    if len(final_training_data) < len(data):
        print(f"Using {len(final_training_data):,} sampled training rows for the final fit to keep runtime practical.")
    model = make_models()[model_name]
    model.fit(final_training_data[features], final_training_data['rul'])
    return model, final_training_data


def feature_importance_summary(model, features: list[str]):
    if not hasattr(model, 'feature_importances_'):
        return []
    importance_df = pd.DataFrame(
        {'feature': features, 'importance': model.feature_importances_}
    ).sort_values('importance', ascending=False)
    return [
        {'feature': row.feature, 'importance': float(row.importance)}
        for row in importance_df.head(12).itertuples()
    ]


def grouped_driver_importance(model, features: list[str]):
    if not hasattr(model, 'feature_importances_'):
        return {}
    feature_to_importance = dict(zip(features, model.feature_importances_))
    groups = {
        'temperature_related': [
            'temperature',
            'rolling_temperature',
            'thermal_stress_index',
            'temperature_soc_interaction',
            'temperature_stress_factor',
        ],
        'dod_related': [
            'dod',
            'avg_dod',
            'capacity_fade',
            'capacity_margin_to_eol',
            'dod_stress_factor',
            'equivalent_full_cycles',
        ],
        'c_rate_related': [
            'c_rate',
            'charge_rate_mean',
            'c_rate_stress_factor',
            'power_draw',
            'current_abs',
        ],
        'voltage_current_state': [
            'voltage',
            'current',
            'rolling_voltage_avg',
            'voltage_drop_from_avg',
            'soc',
        ],
        'health_and_rul_proxy': [
            'capacity_remaining',
            'health_score',
            'degradation_rate_est',
            'physics_rul_proxy',
            'remaining_calendar_months_proxy',
        ],
    }
    return {
        group_name: float(sum(feature_to_importance.get(feature, 0.0) for feature in feature_list))
        for group_name, feature_list in groups.items()
    }


def baseline_metrics(train_data: pd.DataFrame, eval_data: pd.DataFrame):
    inferred_eol_cycle = float(train_data.groupby('battery_id')['cycle_number'].max().median())
    baseline_pred = np.maximum(0, inferred_eol_cycle - eval_data['cycle_number'].to_numpy())
    metrics = evaluate_model(eval_data['rul'], baseline_pred)
    metrics['assumed_eol_cycle'] = inferred_eol_cycle
    return metrics


def build_uncertainty_profile(y_true: pd.Series | np.ndarray, y_pred: pd.Series | np.ndarray):
    interval_alpha = 0.1
    calibration_df = pd.DataFrame({
        'actual_rul': np.asarray(y_true, dtype=float),
        'predicted_rul': np.asarray(y_pred, dtype=float),
    })
    calibration_df['residual'] = calibration_df['actual_rul'] - calibration_df['predicted_rul']
    bins = {
        'near_eol': calibration_df[calibration_df['predicted_rul'] <= 500],
        'mid_life': calibration_df[(calibration_df['predicted_rul'] > 500) & (calibration_df['predicted_rul'] <= 2000)],
        'early_life': calibration_df[calibration_df['predicted_rul'] > 2000],
    }
    profile = {
        'interval_alpha': interval_alpha,
        'overall': {
            'lower_residual_q': float(calibration_df['residual'].quantile(interval_alpha)),
            'upper_residual_q': float(calibration_df['residual'].quantile(1 - interval_alpha)),
        },
        'by_prediction_band': {},
    }
    for band_name, subset in bins.items():
        if len(subset) < 20:
            continue
        profile['by_prediction_band'][band_name] = {
            'lower_residual_q': float(subset['residual'].quantile(interval_alpha)),
            'upper_residual_q': float(subset['residual'].quantile(1 - interval_alpha)),
            'count': int(len(subset)),
        }
    return profile


def summarize_feature_ranges(data: pd.DataFrame, features: list[str]):
    summary = {}
    for feature in features:
        series = data[feature]
        summary[feature] = {
            'min': float(series.min()),
            'max': float(series.max()),
            'mean': float(series.mean()),
            'std': float(series.std()) if not pd.isna(series.std()) else 0.0,
        }
    return summary


def prediction_intervals(predictions: np.ndarray, uncertainty_profile: dict):
    lower = []
    upper = []
    for pred in predictions:
        if pred <= 500:
            band = 'near_eol'
        elif pred <= 2000:
            band = 'mid_life'
        else:
            band = 'early_life'
        band_profile = uncertainty_profile.get('by_prediction_band', {}).get(band, uncertainty_profile['overall'])
        lower.append(max(0.0, pred + band_profile['lower_residual_q']))
        upper.append(max(0.0, pred + band_profile['upper_residual_q']))
    return np.array(lower), np.array(upper)


def interval_coverage(y_true: pd.Series, lower: np.ndarray, upper: np.ndarray):
    within = (y_true.to_numpy() >= lower) & (y_true.to_numpy() <= upper)
    return float(np.mean(within))


def lifecycle_slice_metrics(y_true: pd.Series, y_pred: np.ndarray):
    eval_df = pd.DataFrame({'rul': y_true.to_numpy(), 'pred': y_pred})
    slices = {
        'near_eol': eval_df[eval_df['rul'] <= 500],
        'mid_life': eval_df[(eval_df['rul'] > 500) & (eval_df['rul'] <= 2000)],
        'early_life': eval_df[eval_df['rul'] > 2000],
    }
    metrics = {}
    for name, subset in slices.items():
        if len(subset) >= 2:
            metrics[name] = evaluate_model(subset['rul'], subset['pred'])
            metrics[name]['count'] = int(len(subset))
    return metrics


def train(
    data_path: str,
    model_path='models/rul_model.pkl',
    metrics_out='models/training_metrics.json',
    test_data_path: str = None,
    deployability_out: str = str(DEFAULT_DEPLOYABILITY_PATH),
):
    data_path = resolve_project_path(data_path)
    model_path = resolve_project_path(model_path)
    metrics_out = resolve_project_path(metrics_out)
    test_data_path = resolve_project_path(test_data_path) if test_data_path else None
    deployability_out = resolve_project_path(deployability_out)

    data, features = prepare_data(data_path)
    if 'battery_id' not in data.columns:
        raise ValueError('Grouped evaluation requires a battery_id column in the training dataset.')

    validation_data = maybe_downsample_rows(data, FINAL_TRAIN_SAMPLE_SIZE)
    if len(validation_data) < len(data):
        print(f"Using {len(validation_data):,} sampled training rows for grouped validation.")

    candidate_models = make_models()
    validation_results = grouped_validation_metrics(validation_data, features, candidate_models)

    best_name = min(validation_results, key=lambda name: validation_results[name]['mean_RMSE'])
    best_rmse = validation_results[best_name]['mean_RMSE']
    uncertainty_profile = validation_results[best_name]['uncertainty_profile']
    for name, model_metrics in validation_results.items():
        print(f"{name} grouped validation:")
        print(f"  RMSE: {model_metrics['mean_RMSE']:.4f}")
        print(f"  MAE: {model_metrics['mean_MAE']:.4f}")
        print(f"  R2: {model_metrics['mean_R2']:.4f}")

    best_model, final_training_data = fit_final_model(best_name, data, features)

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    model_bundle = {
        'model': best_model,
        'model_name': best_name,
        'features': features,
        'feature_ranges': summarize_feature_ranges(data, features),
        'uncertainty_profile': uncertainty_profile,
        'feature_importance': feature_importance_summary(best_model, features),
        'driver_importance_groups': grouped_driver_importance(best_model, features),
        'training_rows': int(len(final_training_data)),
        'source_train_data': data_path,
    }
    joblib.dump(model_bundle, model_path)
    print('Best model:', best_name, 'saved to', model_path)

    training_results = {
        'best_model': best_name,
        'best_rmse': best_rmse,
        'grouped_validation': validation_results,
        'features_used': features,
        'feature_importance': feature_importance_summary(best_model, features),
        'driver_importance_groups': grouped_driver_importance(best_model, features),
        'training_rows': int(len(data)),
        'final_fit_rows': int(len(final_training_data)),
        'uncertainty_profile': uncertainty_profile,
    }

    if test_data_path:
        test_data, _ = prepare_data(test_data_path)
        X_test = test_data[features]
        y_test = test_data['rul']
        test_predictions = np.maximum(0.0, best_model.predict(X_test))
        lower_bounds, upper_bounds = prediction_intervals(test_predictions, uncertainty_profile)
        test_metrics = evaluate_model(y_test, test_predictions)
        training_results['test_metrics'] = test_metrics
        training_results['test_error_distribution'] = error_distribution(y_test, test_predictions)
        training_results['test_lifecycle_metrics'] = lifecycle_slice_metrics(y_test, test_predictions)
        training_results['baseline_test_metrics'] = baseline_metrics(data, test_data)
        training_results['test_interval_metrics'] = {
            'coverage': interval_coverage(y_test, lower_bounds, upper_bounds),
            'mean_interval_width': float(np.mean(upper_bounds - lower_bounds)),
        }
        print('Test file metrics:')
        print(f"  RMSE: {test_metrics['RMSE']:.4f}")
        print(f"  MAE: {test_metrics['MAE']:.4f}")
        print(f"  R2: {test_metrics['R2']:.4f}")

    os.makedirs(os.path.dirname(metrics_out), exist_ok=True)
    with open(metrics_out, 'w') as f:
        json.dump(training_results, f, indent=2)
    print('Training metrics saved to', metrics_out)

    deployability_report = build_deployability_report(model_bundle, final_training_data)
    os.makedirs(os.path.dirname(deployability_out), exist_ok=True)
    with open(deployability_out, 'w') as f:
        json.dump(deployability_report, f, indent=2)
    print('Deployability report saved to', deployability_out)

    return training_results


def main():
    parser = argparse.ArgumentParser(description='Train RUL model')
    parser.add_argument('--data', default=str(DEFAULT_TRAIN_DATA), help='Path to CSV training dataset')
    parser.add_argument('--test-data', default=str(DEFAULT_TEST_DATA), help='Optional test CSV dataset')
    parser.add_argument('--model', default=str(DEFAULT_MODEL_PATH), help='Save model path')
    parser.add_argument('--metrics', default=str(DEFAULT_METRICS_PATH), help='JSON metrics output path')
    parser.add_argument('--deployability', default=str(DEFAULT_DEPLOYABILITY_PATH), help='JSON deployability output path')
    args = parser.parse_args()
    results = train(args.data, args.model, args.metrics, test_data_path=args.test_data, deployability_out=args.deployability)
    print('\nModel Evaluation Results:')
    print(f"Best model: {results['best_model']}")
    print(f"Grouped Validation RMSE: {results['best_rmse']:.4f}")
    for model_name, m in results['grouped_validation'].items():
        print(f"{model_name}: RMSE={m['mean_RMSE']:.4f}, MAE={m['mean_MAE']:.4f}, R2={m['mean_R2']:.4f}")
    if 'test_metrics' in results:
        t = results['test_metrics']
        print('Test metrics:')
        print(f"  RMSE: {t['RMSE']:.4f}")
        print(f"  MAE: {t['MAE']:.4f}")
        print(f"  R2: {t['R2']:.4f}")


if __name__ == '__main__':
    main()
