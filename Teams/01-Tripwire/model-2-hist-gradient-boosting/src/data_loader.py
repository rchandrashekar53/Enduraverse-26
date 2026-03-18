from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

from nasa_battery_rul.data_loader import load_and_map_cycle_csv

def load_and_map(path):
    return load_and_map_cycle_csv(path)
