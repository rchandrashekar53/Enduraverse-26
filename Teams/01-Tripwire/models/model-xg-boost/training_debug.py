import traceback
import pandas as pd
import src.rul_prediction_model as m

try:
    df = pd.read_csv('data/synthetic_battery_data_features.csv')
    model, metrics = m.train_rul_model(df)
    print(metrics)
    import os
    print('model saved', os.path.exists('models/rul_model.pkl'))
except Exception:
    traceback.print_exc()
