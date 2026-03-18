from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

import pandas as pd
from nasa_battery_rul.preprocessing import prepare_uploaded_frame

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    return df.copy()

def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    numeric = df.select_dtypes(include=['number']).columns
    result = df.copy()
    if len(numeric) > 0:
        result[numeric] = result[numeric].fillna(result[numeric].median())
    return result.fillna(method='ffill').fillna(method='bfill')

def add_features_passthrough(df: pd.DataFrame):
    normalized, model_1, model_2, _, _ = prepare_uploaded_frame(df)
    return normalized, model_1, model_2

def create_features(df: pd.DataFrame) -> pd.DataFrame:
    normalized, _, _ = add_features_passthrough(df)
    return normalized

def estimate_rul(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if 'rul_cycles' not in result.columns and 'cycle_index' in result.columns:
        max_cycle = float(result['cycle_index'].max()) if len(result) else 0.0
        result['rul_cycles'] = (max_cycle - result['cycle_index']).clip(lower=0.0)
    return result
