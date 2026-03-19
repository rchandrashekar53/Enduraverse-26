# Battery RUL Dashboard and Model Details

## Purpose of This Document

This document explains:

- what each important input and engineered feature means
- what each dashboard graph or table shows
- how each graph is generated
- how the model is trained, validated, tested, and deployed
- what the prediction outputs mean

It is intended as a technical reference for project review, hackathon presentation backup, and teammate onboarding.

## System Overview

The project predicts Remaining Useful Life (RUL) of a lithium-ion battery pack using cycle-level operating data from EV/BMS-style measurements.

The workflow is:

1. Load raw battery CSV data
2. Map column aliases into a standard schema
3. Clean data and fill missing values
4. Engineer degradation-aware features
5. Train battery-grouped ML models
6. Select the best model using grouped validation RMSE
7. Evaluate on a held-out battery test split
8. Save model, metrics, deployability report, plots, and dashboard-ready outputs

## Main Input Schema

The dashboard and CLI prediction flow expect a cycle-level CSV. The most compatible schema is:

```csv
battery_id,cycle,cell_voltage,pack_voltage,pack_current,cell_temperature,soc,dod,c_rate,soh_pct,rul_cycles
```

Minimum practical fields for prediction:

- `battery_id`
- `cycle` or `cycle_number`
- voltage field such as `cell_voltage`, `pack_voltage`, or `voltage`
- current field such as `pack_current`, `cell_current`, or `current`
- temperature field such as `cell_temperature`, `cell_temp`, `temperature`, or `temp`
- `soc`
- `dod`
- `c_rate`
- `soh_pct` or another capacity-health equivalent

Optional but useful:

- `rul_cycles` or `rul` for actual-vs-predicted comparison

## Raw Operational Features

These are the main raw or mapped features used from battery/BMS data.

### `battery_id`

- What it is: Battery or pack identifier
- Why it matters: Used for battery-level grouping, grouped validation, and battery-aware rolling features
- How it is used: Prevents leakage across batteries and supports fleet views in the dashboard

### `cycle_number`

- What it is: Charge-discharge cycle count
- Why it matters: Core degradation progression variable
- How it is used: Base feature, used in trend features, RUL progression, and failure curves

### `voltage`

- What it is: Battery or cell voltage after column mapping
- Why it matters: Indicates electrical operating state and stress
- How it is used: Used directly and in rolling averages and power-related features

### `current`

- What it is: Battery current after column mapping
- Why it matters: Higher current usually increases battery stress and throughput
- How it is used: Used directly, in power calculation, energy throughput, and absolute current feature

### `temperature`

- What it is: Battery or cell temperature
- Why it matters: Temperature accelerates degradation and is one of the main stressors in the hackathon brief
- How it is used: Used directly, in rolling averages, thermal stress, and Arrhenius-style temperature stress factor

### `soc`

- What it is: State of Charge
- Why it matters: Operating window and thermal/electrochemical stress depend on SOC
- How it is used: Used directly and in the `temperature_soc_interaction` feature

### `dod`

- What it is: Depth of Discharge
- Why it matters: Deep cycling increases degradation
- How it is used: Used directly, in average DoD, equivalent full cycles, and DoD stress features

### `c_rate`

- What it is: Charge/discharge rate normalized by capacity
- Why it matters: High C-rate increases internal battery stress and thermal load
- How it is used: Used directly, in rolling mean, and C-rate stress features

### `capacity_remaining`

- What it is: Remaining usable capacity or SoH converted to percentage
- Why it matters: End-of-life is defined at 80% capacity
- How it is used: Used directly, in health score, capacity fade, margin to EOL, business rules, and failure curve

### `rul`

- What it is: Remaining Useful Life target in cycles
- Why it matters: Supervised training target
- How it is used: Used for grouped validation, final test evaluation, actual-vs-predicted plot, and error distribution

## Engineered Features Used by the Model

These are created in [preprocessing.py](C:/Users/user/Desktop/hackathon_final/battery-rul-hackathon/src/preprocessing.py).

### `cycle_age`

- Formula: `cycle_age = cycle_number`
- Role: Explicit age feature for tree-based models

### `rolling_temperature`

- Formula: 30-cycle rolling mean of `temperature`, calculated separately per `battery_id`
- Role: Smooths thermal behavior and captures persistent exposure

### `rolling_voltage_avg`

- Formula: 30-cycle rolling mean of `voltage`, per battery
- Role: Captures drift in electrical behavior over aging

### `avg_dod`

- Formula: Expanding mean of `dod`, per battery
- Role: Captures historical discharge severity

### `charge_rate_mean`

- Formula: 30-cycle rolling mean of `c_rate`, per battery
- Role: Captures typical charging/discharge aggression

### `energy_throughput`

- Formula: cumulative sum of `abs(current) * voltage / 3600`, per battery
- Role: Proxy for total electrical work done by the battery

### `power_draw`

- Formula: `abs(current) * voltage`
- Role: Instantaneous electrical load proxy

### `temperature_soc_interaction`

- Formula: `temperature * soc`
- Role: Captures compounding electrochemical stress at higher temperature and SOC

### `voltage_drop_from_avg`

- Formula: `voltage - rolling_voltage_avg`
- Role: Captures short-term deviation from recent voltage behavior

### `temperature_stress_factor`

- Generated by: `exp((temperature - 25) / 28)`
- Role: Approximate Arrhenius-like thermal acceleration

### `dod_stress_factor`

- Generated by: nonlinear penalty relative to 80% DoD reference
- Role: Penalizes deeper cycling

### `c_rate_stress_factor`

- Generated by: nonlinear penalty for high C-rate
- Role: Captures faster degradation under aggressive operation

### `equivalent_full_cycles`

- Formula: `cycle_number * clip(dod / 100, 0.1, 1.0)`
- Role: Converts partial cycling behavior into a normalized cycle-aging measure

### `combined_stress_index`

- Formula: `temperature_stress_factor * dod_stress_factor * c_rate_stress_factor`
- Role: Single compact stress feature combining the main degradation drivers

### `capacity_fade`

- Formula: `100 - capacity_remaining`
- Role: Amount of capacity loss relative to nominal initial capacity

### `capacity_fade_rate`

- Formula: absolute first difference of `capacity_fade`, per battery
- Role: Captures acceleration or instability in capacity loss

### `capacity_margin_to_eol`

- Formula: `max(0, capacity_remaining - 80)`
- Role: How much capacity remains before the EOL threshold

### `degradation_rate_est`

- Formula: `capacity_fade / cycle_number_safe`
- Role: Average degradation per cycle proxy

### `physics_rul_proxy`

- Formula: `capacity_margin_to_eol / degradation_rate_est`, clipped to `[0, 5000]`
- Role: Physics-inspired approximation of cycles left before 80% capacity

### `remaining_calendar_months_proxy`

- Formula: `physics_rul_proxy / 30`
- Role: Rough conversion from cycle-based life to calendar-month style estimate

### `thermal_stress_index`

- Formula: rolling standard deviation of `temperature`, per battery
- Role: Captures thermal variability and instability

### `current_abs`

- Formula: `abs(current)`
- Role: Battery stress is often more related to current magnitude than sign

### `health_score`

- Formula: `clip(100 - capacity_fade, 0, 100)`
- Role: Simplified health indicator used in both model and dashboard

## Prediction Output Fields

These appear in [predictions.csv](C:/Users/user/Desktop/hackathon_final/battery-rul-hackathon/results/predictions.csv) and the dashboard.

### `predicted_rul`

- Meaning: Model-estimated remaining useful life in cycles
- Generation: `model.predict(features)` with values clamped to `>= 0`

### `predicted_rul_lower` and `predicted_rul_upper`

- Meaning: Lower and upper uncertainty bounds
- Generation: Derived from grouped-validation residual quantiles by prediction band

### `prediction_interval_width`

- Meaning: Width of the uncertainty interval
- Formula: `predicted_rul_upper - predicted_rul_lower`

### `confidence_band`

- Meaning: Human-readable confidence category
- Rules:
  - `High` if width <= 150
  - `Medium` if width <= 350
  - `Low` otherwise

### `predicted_rul_months`

- Meaning: Approximate months of life remaining
- Formula: `predicted_rul / 30`
- Note: This is an operational approximation, not a true calendar-aging model

### `energy_margin_to_eol_kwh`

- Meaning: Approximate energy margin before reaching the 80% EOL threshold for a 35 kWh pack
- Formula: `max(0, (capacity_remaining - 80) / 100 * 35)`

### `ood_feature_count`

- Meaning: Number of features outside the training range envelope
- Generation: Compares uploaded/prediction-time features to training min/max range with a margin

### `is_out_of_distribution`

- Meaning: Whether the sample appears outside the training feature domain
- Formula: `ood_feature_count > 0`

### `battery_health_class`

- Meaning: Business-friendly health category
- Rules:
  - `Critical` if capacity <= 82 or RUL < 500
  - `Moderate` if capacity <= 90 or RUL < 1200
  - `Healthy` otherwise

### `maintenance_recommendation`

- Meaning: Action recommendation for operators
- Generation: Rule-based logic using capacity, RUL, and OOD flag

### `warranty_risk`

- Meaning: Risk category for warranty exposure
- Rules:
  - `High` if RUL < 500 or capacity <= 82
  - `Medium` if RUL < 1000 or confidence is low
  - `Low` otherwise

### `replace_soon_flag`

- Meaning: Boolean flag indicating likely near-term replacement need
- Rule: `predicted_rul < 500`

### `fleet_priority_score`

- Meaning: A simple prioritization score for fleet maintenance ranking
- Generation: Higher when predicted RUL is low and capacity is close to EOL

## Dashboard Elements

The dashboard is implemented in [app.py](C:/Users/user/Desktop/hackathon_final/battery-rul-hackathon/dashboard/app.py).

### Hero KPI Cards

Displayed metrics:

- `Battery Spotlight`
- `Selected Cycle RUL`
- `Test RMSE`
- `Interval Coverage`

What they mean:

- provide the current focus battery, cycle-specific RUL, model quality, and uncertainty quality

How generated:

- read from selected dashboard row and saved training metrics JSON

### Battery Storyline Panel

What it shows:

- selected battery
- selected cycle
- selected predicted RUL
- uncertainty interval
- capacity remaining
- OOD flags
- months left
- energy to EOL
- health class
- warranty risk
- actual RUL and prediction error if labels exist
- maintenance recommendation

How generated:

- based on the currently selected battery and cycle from the sidebar

### RUL Forecast With Confidence Envelope

What it is:

- line chart of predicted RUL over cycle number for one selected battery
- shaded uncertainty band
- actual RUL overlay if available
- marker for the selected cycle

How generated:

- function: `chart_rul_band(...)`
- data source: prediction output frame grouped by `battery_id`

### Battery and Cycle Detail Explorer

What it is:

- tabular inspection tool for any battery and any selected cycle
- shows the selected row transposed as a feature/value table
- also shows neighboring rows around the selected cycle

How generated:

- dashboard slices the battery-specific prediction frame by selected cycle and local row window

### Actual vs Predicted RUL

What it is:

- scatter plot of ground truth vs model prediction
- includes an ideal diagonal line

Why useful:

- shows calibration quality and overall fit

How generated:

- function: `chart_actual_vs_predicted(...)`
- uses a random sample of up to 7000 rows from prediction results

### Fleet Attention Board

What it is:

- horizontal bar chart of the batteries with the lowest predicted RUL
- colored by urgency category

Why useful:

- supports fleet triage and maintenance prioritization

How generated:

- function: `chart_battery_leaderboard(...)`
- built from the latest cycle per battery

### Grouped Validation Model Comparison

What it is:

- grouped bar chart comparing RF and XGB on validation RMSE and MAE

Why useful:

- shows why the selected final model won

How generated:

- function: `chart_validation_comparison(...)`
- reads `grouped_validation` from the saved training metrics file

### Error Profile Across Battery Lifecycle

What it is:

- bar chart showing RMSE in `near_eol`, `mid_life`, and `early_life` segments

Why useful:

- shows where the model is strongest and weakest

How generated:

- function: `chart_lifecycle_metrics(...)`
- uses lifecycle-sliced test metrics generated during training

### Failure Prediction Curve

What it is:

- line chart of `capacity_remaining` vs `cycle_number`
- includes a horizontal 80% EOL line

Why useful:

- directly aligns with the hackathon requirement to show degradation behavior and EOL threshold

How generated:

- function: `plot_failure_curve(...)`
- uses the currently selected battery history

### Top Model Drivers

What it is:

- feature importance bar chart from the trained tree model

Why useful:

- supports explainability and review of what the model is actually using

How generated:

- function: `chart_feature_importance(...)`
- reads `model.feature_importances_` from the saved model bundle

### Grouped Degradation Drivers

What it is:

- grouped importance chart for high-level driver themes:
  - temperature-related
  - DoD-related
  - C-rate-related
  - voltage/current/state
  - health and RUL proxy

Why useful:

- easier for judges and non-ML reviewers than raw feature names alone

How generated:

- created during training by summing feature importances into driver groups
- displayed by `chart_driver_groups(...)`

### Capacity Remaining vs Predicted RUL

What it is:

- scatter plot of `capacity_remaining` vs `predicted_rul`
- colored by confidence band

Why useful:

- visually connects SoH degradation to remaining life

How generated:

- function: `chart_capacity_vs_rul(...)`
- uses a random sample of the prediction frame

### Sensitivity: Temperature vs DoD vs Predicted Life

What it is:

- 3D sensitivity plot across temperature, DoD, and C-rate

Why useful:

- directly addresses the hackathon requirement for sensitivity analysis

How generated:

- function: `conduct_sensitivity_analysis(...)`
- creates a grid over:
  - temperature = `[25, 30, 35, 40, 45]`
  - DoD = `[20, 40, 60, 80]`
  - C-rate = `[0.4, 0.8, 1.2, 1.6]`
- predicted life is computed from the combined degradation stress factors

### Sensitivity Heatmap

What it is:

- heatmap of predicted life vs temperature and DoD

Why useful:

- simpler 2D interpretation of the same sensitivity analysis

How generated:

- same synthetic sensitivity grid as the 3D plot

### Fleet Snapshot Table

What it is:

- latest status per battery
- includes RUL, lower/upper bounds, capacity, confidence, health, warranty risk, and maintenance recommendation

Why useful:

- final fleet-level business and operations view

## Model Training Pipeline

The training pipeline is implemented in [train_model.py](C:/Users/user/Desktop/hackathon_final/battery-rul-hackathon/train_model.py).

### Step 1: Load and Map Data

- raw CSV is loaded
- alias mapping converts fields like `cell_temperature` -> `temperature`, `pack_current` -> `current`, and `rul_cycles` -> `rul`

### Step 2: Clean and Fill Data

- duplicates are removed
- numeric coercion is applied where possible
- missing numeric columns are filled with median
- missing `cycle_number` values are forward/backward filled

### Step 3: Create Features

- all engineered degradation features described above are added
- rolling features are computed per battery, not globally

### Step 4: Prepare Supervised Dataset

- only rows with complete feature values and target `rul` are used

### Step 5: Grouped Validation

- validation uses `GroupShuffleSplit`
- grouping variable is `battery_id`
- this prevents train/validation leakage between cycles of the same battery

### Step 6: Candidate Models

Models trained:

- `RandomForestRegressor`
- `XGBRegressor`

Selection rule:

- best grouped validation RMSE wins

### Step 7: Final Fit

- best model is retrained on a sampled but battery-balanced subset of the train data
- the subset keeps runtime practical while preserving broad coverage

### Step 8: Final Test

- final test file is untouched during model selection
- metrics are computed only after model choice is finalized

### Step 9: Extra Reports

Generated during training:

- grouped validation metrics
- feature importance
- grouped driver importance
- uncertainty profile
- lifecycle-sliced test metrics
- baseline comparison
- error distribution summary
- deployability report

## Training and Test Metrics

Current saved results from [training_metrics.json](C:/Users/user/Desktop/hackathon_final/battery-rul-hackathon/models/training_metrics.json):

- Best model: `xgb`
- Grouped validation RMSE: `197.01`
- Grouped validation MAE: `132.76`
- Grouped validation R2: `0.9780`
- Final test RMSE: `199.43`
- Final test MAE: `133.56`
- Final test R2: `0.9774`
- Interval coverage: `80.06%`
- Mean interval width: `442.28`

Lifecycle-specific test performance:

- Near EOL RMSE: about `33.51`
- Mid-life RMSE: about `154.88`
- Early-life RMSE: about `245.97`

Interpretation:

- model is strongest near end-of-life
- model is weaker in early-life predictions, which is normal because long-horizon degradation is harder to infer

## Uncertainty Generation

Uncertainty is not produced by a probabilistic model directly.

Instead:

1. Out-of-fold validation predictions are collected
2. Residuals are measured: `actual_rul - predicted_rul`
3. Residual quantiles are computed overall and by prediction band:
   - `near_eol`
   - `mid_life`
   - `early_life`
4. These quantiles are added back around each prediction to form lower/upper interval bounds

This gives a practical, lightweight interval estimate suitable for a hackathon and fleet analytics dashboard.

## Deployability Details

Deployability report from [deployability_report.json](C:/Users/user/Desktop/hackathon_final/battery-rul-hackathon/models/deployability_report.json):

- Required BMS columns available: `100%`
- Single prediction latency: about `3.31 ms`
- Estimated 1000-vehicle scoring mean: about `4.90 ms`
- Predictions per second estimate: about `204k`

Current robustness strategies:

- column alias mapping for flexible input schema
- median fill for missing numeric values
- forward/backward fill for missing cycle number
- OOD feature flagging
- business fallback defaults when capacity is missing

## Batch Testing

Batch testing is supported in [predict_rul.py](C:/Users/user/Desktop/hackathon_final/battery-rul-hackathon/predict_rul.py).

You can score multiple CSVs in one directory and automatically produce:

- per-file predictions
- per-file metrics
- per-file evaluation plots
- a combined `batch_summary.csv`

## Saved Plot Outputs

Generated under [results/plots](C:/Users/user/Desktop/hackathon_final/battery-rul-hackathon/results/plots):

- `actual_vs_predicted.html`
- `error_distribution.html`
- `failure_curve.html`

These are useful as backup material outside Streamlit.

## Limitations and Honest Notes

- The dataset is still relatively clean and structured compared to real field telemetry.
- The model currently depends strongly on capacity-derived proxy features such as `health_score`, `physics_rul_proxy`, and `remaining_calendar_months_proxy`.
- Calendar life is approximated from cycle life, not modeled independently.
- A true production deployment would still need stronger field validation, drift monitoring, and savings quantification.

## Recommended Use of This Document

Use this file when:

- a judge asks how a graph is produced
- a teammate asks what a feature means
- you need to explain the training/testing logic clearly
- you want a backup technical note during the final presentation
