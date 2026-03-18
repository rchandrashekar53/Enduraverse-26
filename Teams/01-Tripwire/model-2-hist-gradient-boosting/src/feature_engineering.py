from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

from src.preprocessing import add_features_passthrough

def add_features(df):
    normalized, _, _ = add_features_passthrough(df)
    return normalized
