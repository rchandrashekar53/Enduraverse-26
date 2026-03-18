from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

from src.ml_models import selected_model_name

def bundle_summary(model_key: str) -> dict:
    return {
        'model_key': model_key,
        'selected_model_name': selected_model_name(model_key),
        'bundle_mode': 'scaffold_only',
    }
