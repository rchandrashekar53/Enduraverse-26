import os
import pandas as pd
from src.data_loader import load_and_map
from src.preprocessing import clean_data, handle_missing_values, create_features, estimate_rul
from src.health_score import compute_health_score
from src.rul_prediction_model import train_rul_model
from src.feature_engineering import add_features


def run_pipeline(data_path='data/example_midc_dataset.csv', model_out='models/rul_model.pkl'):
    os.makedirs('models', exist_ok=True)
    os.makedirs('results', exist_ok=True)
    print('Loading dataset:', data_path)
    df_raw, mapping, missing = load_and_map(data_path)
    print('Mapped columns:', mapping)
    if missing:
        print('Missing columns:', missing)
    df = clean_data(df_raw)
    df = handle_missing_values(df)
    df = add_features(df)
    df = create_features(df)
    df = compute_health_score(df)
    df = estimate_rul(df)

    if 'rul' not in df.columns:
        print('No RUL in data; cannot train supervision-based models.')
        return

    model, metrics = train_rul_model(df, save_path=model_out)
    print('Training complete. Model saved to', model_out)
    print('Metrics:', metrics)
    df.to_csv('results/pipeline_processed.csv', index=False)
    print('Processed data saved to results/pipeline_processed.csv')
    return df, model, metrics

if __name__ == '__main__':
    run_pipeline()
