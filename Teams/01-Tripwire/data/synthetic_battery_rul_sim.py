import numpy as np
import pandas as pd

#dataset generation code

MIDC_TIME_S = np.array(
    [
        0, 10, 20, 30, 40, 50, 60, 70, 90, 110, 130, 150, 170, 200, 230, 260,
        300, 340, 380, 420, 460, 500, 540, 580, 620, 660, 700, 760, 820, 880,
        940, 1000, 1060, 1080
    ],
    dtype=float,
)
MIDC_SPEED_KMH = np.array(
    [
        0, 10, 20, 30, 35, 30, 25, 0, 15, 30, 40, 50, 45, 35, 25, 10, 0, 20, 35,
        45, 55, 60, 55, 45, 35, 20, 0, 20, 35, 50, 60, 40, 20, 0
    ],
    dtype=float,
)


def build_midc_current_shape(time_s: np.ndarray, speed_kmh: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    
    v_ms = speed_kmh * (1000.0 / 3600.0)
    dt = np.diff(time_s, prepend=time_s[0])
    dt[0] = np.median(np.diff(time_s))
    acc = np.gradient(v_ms, time_s)

    v_norm = v_ms / (np.max(v_ms) + 1e-9)
    acc_pos = np.clip(acc, 0.0, None)
    acc_neg = np.clip(-acc, 0.0, None)
    acc_pos_norm = acc_pos / (np.max(acc_pos) + 1e-9)
    acc_neg_norm = acc_neg / (np.max(acc_neg) + 1e-9)

    shape = 0.30 + 0.50 * v_norm + 0.35 * acc_pos_norm - 0.45 * acc_neg_norm
    shape = shape - np.mean(shape) * 0.10
    return shape, dt


def sample_c_rate(rng: np.random.Generator) -> float:
    
    u = rng.random()
    if u < 0.86:
        return 0.2 + 0.6 * rng.beta(2.3, 4.8)
    if u < 0.97:
        return 0.8 + 0.3 * rng.beta(2.0, 2.5)
    return 1.1 + 0.4 * rng.beta(1.8, 2.8)


def sample_dod_pct(rng: np.random.Generator) -> float:
    
    u = rng.random()
    if u < 0.75:
        return 20.0 + 40.0 * rng.beta(2.2, 2.6)
    return 60.0 + 25.0 * rng.beta(2.0, 2.2)


def ocv_cell_from_soc(soc_pct: np.ndarray) -> np.ndarray:
    
    s = np.clip(soc_pct / 100.0, 0.0, 1.0)
    return (
        3.05
        + 0.22 * s
        + 0.05 * np.tanh((s - 0.50) / 0.11)
        + 0.03 * (s - 0.50) ** 2
    )


def simulate_cycle_profiles(
    rng: np.random.Generator,
    current_shape: np.ndarray,
    dt_base: np.ndarray,
    c_rate_target: float,
    dod_target: float,
    soc_start: float,
    capacity_ah: float,
    regen_eff: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    
    i_abs_target = c_rate_target * capacity_ah

    local_shape = current_shape * rng.normal(1.0, 0.05, size=current_shape.shape[0])
    mean_abs = np.mean(np.abs(local_shape)) + 1e-9
    i_profile = (local_shape / mean_abs) * i_abs_target
    i_profile = np.clip(i_profile, -0.45 * i_abs_target, 2.1 * i_abs_target)

    i_dis = np.clip(i_profile, 0.0, None)
    i_reg = -np.clip(i_profile, None, 0.0)
    net_ah_base = np.sum((i_dis - regen_eff * i_reg) * dt_base) / 3600.0

    target_ah = capacity_ah * (dod_target / 100.0)
    dt_scale = target_ah / max(net_ah_base, 1e-9)
    dt_scale = np.clip(dt_scale, 0.60, 4.00)
    dt = dt_base * dt_scale

    step_ah = (i_dis - regen_eff * i_reg) * dt / 3600.0
    soc_trace = soc_start - np.cumsum(step_ah) / capacity_ah * 100.0
    soc_trace = np.clip(soc_trace, 10.0, 100.0)
    dod_actual = float(soc_start - soc_trace[-1])
    return i_profile, dt, soc_trace, dod_actual


def simulate_temperature_profile(
    i_profile: np.ndarray,
    dt: np.ndarray,
    ambient_c: float,
    r_internal_ohm: float,
    rng: np.random.Generator,
) -> np.ndarray:
    
    c_th = 55000.0
    h_cool = 32.0

    temp = np.empty(i_profile.shape[0], dtype=float)
    temp[0] = ambient_c + rng.normal(1.0, 0.6)
    for k in range(1, i_profile.shape[0]):
        q_joule = (i_profile[k - 1] ** 2) * r_internal_ohm
        q_cool = h_cool * (temp[k - 1] - ambient_c)
        dtemp = (q_joule - q_cool) * dt[k] / c_th
        temp[k] = temp[k - 1] + dtemp

    temp = np.clip(temp, ambient_c - 2.0, 56.0)
    return temp


def degradation_per_cycle(
    cycle_idx: int,
    temp_c: float,
    dod_pct: float,
    c_rate: float,
    base_deg_pct: float,
    battery_factor: float,
    rng: np.random.Generator,
) -> float:
    temp_factor = np.exp(0.045 * (temp_c - 25.0))
    dod_factor = np.clip((dod_pct / 45.0) ** 1.35, 0.50, 2.50)
    c_rate_factor = np.clip((c_rate / 0.55) ** 0.85, 0.65, 2.20)
    aging_factor = 1.0 + 0.00022 * cycle_idx
    stochastic = rng.normal(1.0, 0.03)

    delta = (
        base_deg_pct
        * battery_factor
        * temp_factor
        * dod_factor
        * c_rate_factor
        * aging_factor
        * stochastic
    )
    return float(np.clip(delta, 0.0010, 0.0200))


def simulate_battery(
    battery_id: int,
    rng: np.random.Generator,
    current_shape: np.ndarray,
    dt_base: np.ndarray,
    max_cycles: int = 6000,
) -> pd.DataFrame:
    n_series = 110
    v_nom_pack = 352.0
    capacity_ah = 100.0

    r0 = rng.uniform(0.036, 0.052)
    base_deg_pct = rng.uniform(0.0025, 0.0031)
    battery_factor = rng.uniform(0.95, 1.05)
    regen_eff = rng.uniform(0.58, 0.72)

    soh = 100.0
    deg_rate_ema = None
    rows = []

    for cycle in range(1, max_cycles + 1):
        ambient_c = rng.uniform(20.0, 45.0)
        c_rate_target = sample_c_rate(rng)
        dod_target = sample_dod_pct(rng)

        soc_start = rng.uniform(82.0, 92.0)
        dod_target = min(dod_target, soc_start - 10.0)

        i_profile, dt, soc_trace, dod_actual = simulate_cycle_profiles(
            rng=rng,
            current_shape=current_shape,
            dt_base=dt_base,
            c_rate_target=c_rate_target,
            dod_target=dod_target,
            soc_start=soc_start,
            capacity_ah=capacity_ah,
            regen_eff=regen_eff,
        )

        r_internal = r0 * (1.0 + 0.012 * (100.0 - soh))
        temp_trace = simulate_temperature_profile(
            i_profile=i_profile,
            dt=dt,
            ambient_c=ambient_c,
            r_internal_ohm=r_internal,
            rng=rng,
        )

        ocv_cell = ocv_cell_from_soc(soc_trace)
        pack_voltage_trace = n_series * ocv_cell - i_profile * r_internal
        pack_voltage_trace = np.clip(pack_voltage_trace, 280.0, 410.0)

        pack_current = float(np.mean(np.abs(i_profile)))
        c_rate_cycle = float(pack_current / capacity_ah)
        pack_voltage = float(np.mean(pack_voltage_trace))
        cell_voltage = float(pack_voltage / n_series)
        cell_temp = float(np.mean(temp_trace))
        soc_mean = float(np.mean(soc_trace))

        delta_soh = degradation_per_cycle(
            cycle_idx=cycle,
            temp_c=cell_temp,
            dod_pct=dod_actual,
            c_rate=c_rate_cycle,
            base_deg_pct=base_deg_pct,
            battery_factor=battery_factor,
            rng=rng,
        )

        soh_next = soh - delta_soh
        if soh_next <= 80.0:
            soh_next = 80.0

        if deg_rate_ema is None:
            deg_rate_ema = delta_soh
        else:
            deg_rate_ema = 0.90 * deg_rate_ema + 0.10 * delta_soh

        min_deg_rate = 20.0 / 4500.0
        effective_deg_rate = max(deg_rate_ema, min_deg_rate)
        rul_cycles = max((soh_next - 80.0) / effective_deg_rate, 0.0)

        rows.append({
            "battery_id": battery_id,
            "cycle": cycle,
            "cell_voltage": round(cell_voltage, 3),
            "pack_voltage": round(pack_voltage, 2),
            "pack_current": round(pack_current, 2),
            "cell_temperature": round(cell_temp, 1),
            "soc": round(soc_mean, 1),
            "dod": round(dod_actual, 1),
            "c_rate": round(c_rate_cycle, 2),
            "soh_pct": round(soh_next, 2),
            "rul_cycles": int(rul_cycles)
        })

        soh = soh_next
        if soh <= 80.0:
            break

    return pd.DataFrame(rows)


def generate_dataset(
    n_batteries: int = 200,
    seed: int = 42,
    max_cycles: int = 6000,
) -> pd.DataFrame:
    
    rng = np.random.default_rng(seed)
    current_shape, dt_base = build_midc_current_shape(MIDC_TIME_S, MIDC_SPEED_KMH)
    frames = []
    for bid in range(1, n_batteries + 1):
        frames.append(
            simulate_battery(
                battery_id=bid,
                rng=rng,
                current_shape=current_shape,
                dt_base=dt_base,
                max_cycles=max_cycles,
            )
        )
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    df = generate_dataset(n_batteries=200, seed=42, max_cycles=6000)
    out_path = "synthetic_battery_rul.csv"
    try:
        df.to_csv(out_path, index=False)
    except PermissionError:
        out_path = "synthetic_battery_rul.csv"
        df.to_csv(out_path, index=False)

    print(f"Saved: {out_path}")
    print(f"Rows: {len(df):,}")
    print(f"Batteries: {df['battery_id'].nunique()}")
    print("Cycle range per battery (min/max):")
    life = df.groupby("battery_id")["cycle"].max()
    print(int(life.min()), int(life.max()))
    print("Temperature range:", round(df["cell_temperature"].min(), 2), "to", round(df["cell_temperature"].max(), 2))
    print("C-rate range:", round(df["c_rate"].min(), 2), "to", round(df["c_rate"].max(), 2))
    print("SOH range:", round(df["soh_pct"].min(), 2), "to", round(df["soh_pct"].max(), 2))
