from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import numpy as np
import pandas as pd


def evaluate_model(y_true, y_pred):
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    return {
        "RMSE": float(rmse),
        "MAE": float(mae),
        "R2": float(r2),
    }


def error_distribution(y_true, y_pred):
    errors = np.asarray(y_pred) - np.asarray(y_true)
    return {
        "mean_error": float(np.mean(errors)),
        "median_error": float(np.median(errors)),
        "p05_error": float(np.quantile(errors, 0.05)),
        "p95_error": float(np.quantile(errors, 0.95)),
    }


def error_frame(y_true, y_pred):
    return pd.DataFrame(
        {
            "actual_rul": np.asarray(y_true),
            "predicted_rul": np.asarray(y_pred),
            "error": np.asarray(y_pred) - np.asarray(y_true),
            "absolute_error": np.abs(np.asarray(y_pred) - np.asarray(y_true)),
        }
    )
