from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

import json
from pathlib import Path
from src.ml_models import selected_model_name

def train_rul_model(df, save_path='models/rul_model.pkl', model_key='model_1'):
    metrics = {
        'model_name': selected_model_name(model_key),
        'rows': int(len(df)),
        'feature_columns': [column for column in df.columns if column not in {'battery_id', 'rul_cycles'}],
        'artifact_written': False,
        'note': 'Scaffold-only package. Local serialized model intentionally omitted for now.'
    }
    output = Path(save_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output.with_suffix('.json')
    metadata_path.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    return None, metrics
