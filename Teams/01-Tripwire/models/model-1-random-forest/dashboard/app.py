# pyright: reportMissingImports=false
# pyright: reportMissingImports=false
# pyright: reportMissingImports=false
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

from nasa_battery_rul.streamlit_dashboard import run_streamlit_dashboard

if __name__ == '__main__':
    run_streamlit_dashboard(default_dataset_key='battery_set_clean', focus_model='model_1')
