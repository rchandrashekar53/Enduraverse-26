import numpy as np


def build_hybrid_predictions(df, physics_rul_col='physics_rul', features=None, ml_model=None):
    if ml_model is None:
        raise ValueError('ML model required')
    if features is None:
        features = ['cycle_number', 'voltage', 'current', 'temperature', 'soc', 'dod', 'c_rate', 'capacity_remaining']
    x = df[features].fillna(0)
    df = df.copy()
    df['ml_error'] = ml_model.predict(x)
    df['hybrid_rul'] = df[physics_rul_col] + df['ml_error']
    df['hybrid_rul'] = np.maximum(0, df['hybrid_rul'])
    return df
