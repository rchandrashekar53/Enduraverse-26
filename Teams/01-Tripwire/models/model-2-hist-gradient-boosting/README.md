# Model 2 Hist Gradient Boosting

This package is the final Model 2 bundle for the battery RUL hackathon workspace. It is organized as a standalone deliverable with the same visible project layout pattern used across the team packages, while the underlying runtime logic is delegated to the shared repository code in [src](src).

## Purpose

This bundle represents the Stage 2 final model track:

- model family: compact tabular/hybrid decision-engine-aligned supervised model
- final selected estimator: `hist_gradient_boosting`
- primary usage: package-level training/prediction smoke flow, dashboard launch, and judge-facing structure

The package is intended to look and behave like an independent model workspace, but it is still structurally linked to the shared project codebase.

## Technical Summary

- package name: `model-2-hist-gradient-boosting`
- selected estimator: `hist_gradient_boosting`
- prediction task: battery remaining useful life in cycles
- expected target column: `rul_cycles`
- default packaged example input: [data/example_midc_dataset.csv](data/example_midc_dataset.csv)

The bundle pipeline follows this order:

1. load and map battery-cycle columns
2. clean missing values
3. add normalized battery features
4. generate derived feature columns
5. compute health-score proxy
6. ensure `rul_cycles` exists
7. run the packaged training wrapper
8. save processed CSV and bundle metadata outputs

## Data Contract

The packaged loader expects a battery-cycle CSV that can be mapped into the canonical fields below:

- `battery_id`
- `cycle`
- `cell_voltage`
- `pack_current`
- `cell_temperature`
- `soc`
- `dod`
- `c_rate`
- `soh_pct`
- `rul_cycles`

The packaged preprocessing path maps these into the normalized representation used by the shared Model 2 logic. The model track is centered on driver/degradation-state features such as:

- `cycle_index`
- `temperature_mean`
- `voltage_mean`
- `current_mean`
- `soc`
- `dod`
- `c_rate`
- `soh`
- `capacity_ah`
- `duration_s`
- `cohort`
- `load_profile`
- `recent_capacity_slope_5`
- `recent_capacity_slope_10`
- `temperature_stress_cum`
- `life_fraction`

## What The Bundle Scripts Do

### [run_pipeline.py](run_pipeline.py)

This is the main packaged pipeline entrypoint. It mirrors the same top-level style used in the reference project:

- loads the CSV
- prints the mapped columns
- runs cleaning and feature creation
- calls `train_rul_model(...)`
- writes [results/pipeline_processed.csv](results/pipeline_processed.csv)

Current bundle behavior:

- it writes model metadata to [models/rul_model.json](models/rul_model.json)
- it does **not** yet write a real local `rul_model.pkl`

### [train_model.py](train_model.py)

Thin wrapper that calls the packaged pipeline.

### [predict_rul.py](predict_rul.py)

Bundle-local prediction smoke path:

- loads a CSV
- maps and normalizes it
- returns a prediction table
- writes [results/predictions.csv](results/predictions.csv)

Current bundle behavior:

- this is a scaffold prediction path
- it is not yet using a trained local serialized model artifact
- the current smoke path mirrors RUL through the wrapper flow so the bundle can be exercised end-to-end

### [dashboard/app.py](dashboard/app.py)

Launches the shared Streamlit dashboard with focus on Model 2.

## Bundle Structure

- [dashboard](dashboard): packaged Streamlit entrypoint
- [data](data): packaged datasets and static assets
- [docs](docs): bundle documentation
- [models](models): bundle metadata outputs
- [notebooks](notebooks): notebook placeholder
- [results](results): packaged outputs
- [src](src): module names with wrapper implementations
- [utils](utils): utility wrappers
- [model-2-hist-gradient-boosting/results](model-2-hist-gradient-boosting/results): nested self-named results placeholder for layout parity

## Files Written During The Smoke Run

After running the package from inside its folder:

```powershell
python run_pipeline.py
python predict_rul.py
```

the bundle produced:

- [results/pipeline_processed.csv](results/pipeline_processed.csv)
- [models/rul_model.json](models/rul_model.json)
- [results/predictions.csv](results/predictions.csv)

Observed smoke-run metadata:

- `model_name`: `hist_gradient_boosting`
- `rows`: `1000`
- `artifact_written`: `False`

## Commands

Run the packaged pipeline:

```powershell
python run_pipeline.py
```

Run packaged prediction:

```powershell
python predict_rul.py
```

Launch the bundled dashboard:

```powershell
streamlit run dashboard/app.py
```

## Current Limitations

- no local `models/rul_model.pkl` yet
- prediction path is a scaffold smoke path, not final isolated bundle inference
- runtime depends on the shared repository `src` tree
- the package is structurally standalone but not yet artifact-isolated

## What Would Make This Fully Standalone Later

- save a real trained Hist Gradient Boosting pipeline to `models/rul_model.pkl`
- make `predict_rul.py` load only bundle-local artifacts
- make dashboard reads depend on bundle-local outputs rather than shared workspace state
