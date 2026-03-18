from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_SRC = PROJECT_ROOT / 'src'
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

import argparse
import pandas as pd
from src.rul_prediction import predict_rul

parser = argparse.ArgumentParser(description='Predict RUL from a bundle CSV input')
parser.add_argument('--data', default='data/battery_set_clean_test_20.csv')
parser.add_argument('--out', default='results/predictions.csv')
args = parser.parse_args()

if __name__ == '__main__':
    df = pd.read_csv(args.data)
    result = predict_rul(df, model_key='model_2')
    result.to_csv(args.out, index=False)
    print('Predictions saved to', args.out)
