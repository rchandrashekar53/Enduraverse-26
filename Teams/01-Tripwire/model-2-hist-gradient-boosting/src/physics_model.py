from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

"""Physics model wrapper

Wrapper placeholder aligned to the Abhinav folder layout. Shared logic lives in `nasa_battery_rul.preprocessing`.
"""
