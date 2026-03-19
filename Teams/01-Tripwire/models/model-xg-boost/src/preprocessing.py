import numpy as np
import pandas as pd

from src.degradation_model import c_rate_stress_factor, dod_stress_factor, temperature_stress_factor


def _group_series(df: pd.DataFrame):
    if 'battery_id' in df.columns:
        return df.groupby('battery_id', sort=False)
    return None


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    data = data.drop_duplicates().reset_index(drop=True)
    for col in data.columns:
        try:
            data[col] = pd.to_numeric(data[col])
        except (ValueError, TypeError):
            pass
    return data


def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
    for col in numeric_cols:
        if data[col].isna().any():
            data[col] = data[col].fillna(data[col].median())
    if 'cycle_number' in data.columns:
        data['cycle_number'] = data['cycle_number'].ffill().bfill().astype(int)
    return data


def normalize_features(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    data = df.copy()
    if cols is None:
        cols = data.select_dtypes(include=['number']).columns.tolist()
    for col in cols:
        mn = data[col].min()
        mx = data[col].max()
        if mx > mn:
            data[col + '_norm'] = (data[col] - mn) / (mx - mn)
        else:
            data[col + '_norm'] = 0.0
    return data


def create_features(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    battery_groups = _group_series(data)

    if 'cycle_number' in data.columns:
        data['cycle_age'] = data['cycle_number']
    if 'temperature' in data.columns:
        if battery_groups is not None:
            data['rolling_temperature'] = battery_groups['temperature'].transform(
                lambda s: s.rolling(30, min_periods=1).mean()
            )
        else:
            data['rolling_temperature'] = data['temperature'].rolling(30, min_periods=1).mean()
        data['rolling_temperature_avg'] = data['rolling_temperature']
    if 'voltage' in data.columns:
        if battery_groups is not None:
            data['rolling_voltage_avg'] = battery_groups['voltage'].transform(
                lambda s: s.rolling(30, min_periods=1).mean()
            )
        else:
            data['rolling_voltage_avg'] = data['voltage'].rolling(30, min_periods=1).mean()
    if 'dod' in data.columns:
        if battery_groups is not None:
            data['avg_dod'] = battery_groups['dod'].transform(lambda s: s.expanding().mean())
        else:
            data['avg_dod'] = data['dod'].expanding().mean()
    if 'c_rate' in data.columns:
        if battery_groups is not None:
            data['charge_rate_mean'] = battery_groups['c_rate'].transform(
                lambda s: s.rolling(30, min_periods=1).mean().bfill()
            )
        else:
            data['charge_rate_mean'] = data['c_rate'].rolling(30, min_periods=1).mean().bfill()
        data['C_rate'] = data['c_rate']
    if 'current' in data.columns and 'voltage' in data.columns:
        instantaneous_energy = data['current'].abs() * data['voltage']
        if battery_groups is not None:
            data['energy_throughput'] = (
                instantaneous_energy.groupby(data['battery_id'], sort=False).cumsum() / 3600.0
            )
        else:
            data['energy_throughput'] = instantaneous_energy.cumsum() / 3600.0
        data['power_draw'] = instantaneous_energy
        data['temperature_soc_interaction'] = data.get('temperature', 0) * data.get('soc', 0)
        data['voltage_drop_from_avg'] = data['voltage'] - data.get('rolling_voltage_avg', data['voltage'])
    data['temperature_stress_factor'] = temperature_stress_factor(data.get('temperature', 25.0))
    data['dod_stress_factor'] = dod_stress_factor(data.get('dod', 60.0))
    data['c_rate_stress_factor'] = c_rate_stress_factor(data.get('c_rate', 0.7))
    data['equivalent_full_cycles'] = data.get('cycle_number', 0) * np.clip(data.get('dod', 0) / 100.0, 0.1, 1.0)
    data['combined_stress_index'] = (
        data['temperature_stress_factor'] * data['dod_stress_factor'] * data['c_rate_stress_factor']
    )
    if 'capacity_remaining' not in data.columns and 'soh_pct' in data.columns:
        data['capacity_remaining'] = data['soh_pct']
    if 'capacity_remaining' in data.columns:
        if data['capacity_remaining'].max() <= 1.0:
            data['capacity_remaining'] = data['capacity_remaining'] * 100
        data['capacity_fade'] = 100.0 - data['capacity_remaining']
        data['capacity_ratio'] = data['capacity_remaining'] / data['capacity_remaining'].max()
        if battery_groups is not None:
            data['capacity_fade_rate'] = battery_groups['capacity_fade'].transform(lambda s: s.diff().fillna(0).abs())
        else:
            data['capacity_fade_rate'] = data['capacity_fade'].diff().fillna(0).abs()
    else:
        data['capacity_fade'] = 0.0
        data['capacity_ratio'] = 1.0
        data['capacity_fade_rate'] = 0.0
    data['cycle_number_safe'] = data.get('cycle_number', 0).replace(0, 1) if 'cycle_number' in data.columns else 1
    data['capacity_margin_to_eol'] = np.maximum(0.0, data.get('capacity_remaining', 100.0) - 80.0)
    data['degradation_rate_est'] = data.get('capacity_fade', 0.0) / data['cycle_number_safe']
    positive_degradation = data['degradation_rate_est'] > 1e-6
    data['physics_rul_proxy'] = np.where(
        positive_degradation,
        data['capacity_margin_to_eol'] / data['degradation_rate_est'],
        4500.0,
    )
    data['physics_rul_proxy'] = np.clip(data['physics_rul_proxy'], 0.0, 5000.0)
    data['remaining_calendar_months_proxy'] = np.clip(data['physics_rul_proxy'] / 30.0, 0.0, 200.0)
    if 'temperature' in data.columns:
        if battery_groups is not None:
            data['thermal_stress_index'] = battery_groups['temperature'].transform(
                lambda s: s.rolling(30, min_periods=1).std().fillna(0)
            )
        else:
            data['thermal_stress_index'] = data['temperature'].rolling(30, min_periods=1).std().fillna(0)
    else:
        data['thermal_stress_index'] = 0.0
    if 'internal_resistance' not in data.columns:
        data['internal_resistance'] = 0.01 + 0.00005 * data.get('cycle_number', 0)
    data['current_abs'] = data.get('current', 0).abs() if 'current' in data.columns else 0.0
    data['health_score'] = np.clip(100.0 - data.get('capacity_fade', 0.0), 0, 100)
    return data


def estimate_rul(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    if 'rul' in data.columns:
        return data
    if 'cycle_number' not in data.columns or 'capacity_ratio' not in data.columns:
        data['rul'] = pd.NA
        return data

    eol_mask = data['capacity_ratio'] <= 0.8
    if eol_mask.any():
        eol_cycle = data.loc[eol_mask, 'cycle_number'].iloc[0]
    else:
        eol_cycle = data['cycle_number'].max() + 100
    data['rul'] = np.maximum(0, eol_cycle - data['cycle_number'])
    return data
