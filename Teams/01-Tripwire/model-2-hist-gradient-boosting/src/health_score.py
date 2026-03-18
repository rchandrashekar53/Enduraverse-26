from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

def compute_health_score(df):
    result = df.copy()
    if 'soh' in result.columns:
        result['health_score'] = result['soh']
    elif 'soh_pct' in result.columns:
        result['health_score'] = result['soh_pct']
    else:
        result['health_score'] = 1.0
    return result
