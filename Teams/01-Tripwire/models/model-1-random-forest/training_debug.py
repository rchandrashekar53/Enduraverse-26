from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

from src.business_logic import bundle_summary

if __name__ == '__main__':
    print(bundle_summary('model_1'))
