import numpy as np


def compute_health_score(df):
    data = df.copy()
    if 'capacity_remaining' in data.columns:
        data['capacity_ratio'] = data['capacity_remaining'] / data['capacity_remaining'].max()
    else:
        data['capacity_ratio'] = 0.8
    if 'cycle_number' in data.columns:
        data['cycle_health'] = np.clip(1 - (data['cycle_number'] / data['cycle_number'].max()), 0, 1)
    else:
        data['cycle_health'] = 1.0
    if 'temperature' in data.columns:
        data['temperature_stress'] = np.clip((data['temperature'] - 25) / 40, 0, 1)
    else:
        data['temperature_stress'] = 0.0
    data['health_score'] = 100 * (0.5 * data['capacity_ratio'] + 0.3 * data['cycle_health'] + 0.2 * (1 - data['temperature_stress']))
    data['health_score'] = data['health_score'].clip(0, 100)
    return data
