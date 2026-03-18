from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

from nasa_battery_rul.model_selection import FINAL_MODEL_1_NAME, DEFAULT_MODEL_2_NAME

def selected_model_name(model_key: str) -> str:
    return FINAL_MODEL_1_NAME if model_key == 'model_1' else DEFAULT_MODEL_2_NAME
