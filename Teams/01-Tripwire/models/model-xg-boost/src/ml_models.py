import joblib
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split


def train_ml_model(X, y, random_state=42):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=random_state)
    model = XGBRegressor(n_estimators=150, learning_rate=0.08, random_state=random_state, objective='reg:squarederror', n_jobs=-1)
    model.fit(X_train, y_train)
    return model, X_train, X_test, y_train, y_test


def save_model(model, path='models/ml_rul_model.pkl'):
    joblib.dump(model, path)
    return path


def load_model(path='models/ml_rul_model.pkl'):
    return joblib.load(path)
