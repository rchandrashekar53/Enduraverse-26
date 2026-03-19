import numpy as np
from scipy.optimize import curve_fit


def exp_decay(cycle, a, b):
    return a * np.exp(-b * cycle)


def fit_physics_capacity(cycle, capacity):
    cycle = np.array(cycle)
    capacity = np.array(capacity)
    if len(cycle) < 3:
        raise ValueError('Need at least 3 points to fit physics model')
    p0 = [capacity.max(), 1e-3]
    popt, _ = curve_fit(exp_decay, cycle, capacity, p0=p0, maxfev=20000)
    return popt


def predict_capacity(cycle, params):
    a, b = params
    return exp_decay(np.array(cycle), a, b)


def compute_physics_rul(df, params, eol_ratio=0.8):
    predicted = predict_capacity(df['cycle_number'], params)
    init = predicted[0] if len(predicted) > 0 else 100
    threshold = init * eol_ratio
    eol_index = np.argmax(predicted <= threshold) if np.any(predicted <= threshold) else len(predicted)
    if eol_index == 0:
        eol_cycle = df['cycle_number'].iloc[0]
    elif np.any(predicted <= threshold):
        eol_cycle = df['cycle_number'].iloc[eol_index]
    else:
        eol_cycle = df['cycle_number'].iloc[-1] + 100
    df = df.copy()
    df['physics_capacity'] = predicted
    df['physics_rul'] = np.maximum(0, eol_cycle - df['cycle_number'])
    return df
