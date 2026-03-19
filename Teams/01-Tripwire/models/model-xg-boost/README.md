# Battery RUL Hackathon Platform

End-to-end RUL prediction and analytics for eLCV batteries.

## Project structure
- `data/`: Synthetic dataset and outputs
- `src/`: Data simulation, feature engineering, models, analysis
- `dashboard/`: Streamlit app
- `models/`: Saved model
- `utils/`: Shared helpers

## Run it
1. python -m venv venv
2. .\venv\Scripts\activate
3. pip install -r requirements.txt
3. python run_pipeline.py
4. python train_model.py --data data/example_midc_dataset.csv
5. python predict_rul.py --data data/example_midc_dataset.csv
7. streamlit run dashboard/app.py

## New plug-and-play commands
- Train model on any dataset:
  - `python train_model.py --data data/example_midc_dataset.csv`
- Predict RUL on new dataset:
  - `python predict_rul.py --data data/example_midc_dataset.csv`
- Dashboard upload flow:
  - `streamlit run dashboard/app.py`
  - Upload your CSV in the sidebar, then view predictions and visualizations.

## Training and evaluation outputs
- Training metrics JSON: `models/training_metrics.json`
- Prediction outputs: `results/predictions.csv`
- Test metrics JSON: `results/test_metrics.json`

## CLI usage
Train model:
```bash
python train_model.py --data data/example_midc_dataset.csv
```
Predict (with optional true RUL evaluation):
```bash
python predict_rul.py --data data/example_midc_dataset.csv
```

## Example datasets
- `data/example_midc_dataset.csv`
- `data/example_battery_dataset.csv`

