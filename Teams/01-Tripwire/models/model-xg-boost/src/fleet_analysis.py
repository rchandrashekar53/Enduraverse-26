import pandas as pd


def simulate_fleet(df, n=10):
    df = df.copy()
    vehicle_ids = [f"EV-{i+1:03d}" for i in range(n)]
    rows = []
    for vid in vehicle_ids:
        sample = df.sample(frac=0.1, replace=True)
        avg_health = sample['health_score'].mean() if 'health_score' in sample.columns else 50
        avg_rul = sample['rul'].mean() if 'rul' in sample.columns else 300
        rows.append({
            'vehicle_id': vid,
            'battery_health': float(avg_health),
            'predicted_RUL': float(avg_rul),
            'maintenance_alert': 'yes' if avg_health < 60 or avg_rul < 200 else 'no'
        })
    return pd.DataFrame(rows)
