import numpy as np

def calculate_health_score(capacity_remaining, temp_exposure=0, dod=0, c_rate=0):
    base = (capacity_remaining - 60) / 40 * 100
    penalty = temp_exposure * 0.2 + dod * 0.05 + c_rate * 5
    return np.clip(base - penalty, 0, 100)
