from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

import pandas as pd
from nasa_battery_rul.preprocessing import prepare_uploaded_frame
from src.ml_models import selected_model_name

def predict_rul(df: pd.DataFrame, model_key: str = 'model_1') -> pd.DataFrame:
    normalized, model_1, model_2, _, _ = prepare_uploaded_frame(df)
    active = model_1 if model_key == 'model_1' else model_2
    result = active[['battery_id', 'cycle_index']].copy()
    if 'rul_cycles' in active.columns:
        result['rul_cycles'] = active['rul_cycles']
        result['predicted_rul'] = active['rul_cycles']
    else:
        result['predicted_rul'] = 0.0
    result['model_name'] = selected_model_name(model_key)
    return result
