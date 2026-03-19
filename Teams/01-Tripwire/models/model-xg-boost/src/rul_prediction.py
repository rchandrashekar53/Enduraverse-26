import pandas as pd
from src.rul_prediction_model import predict_rul


def execute_prediction(model, df):
    return predict_rul(model, df)

if __name__ == '__main__':
    print('Use predict_rul.py for CLI prediction.')
