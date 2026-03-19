import pandas as pd
from typing import Dict, List, Tuple

COLUMN_ALIASES = {
    'voltage': ['voltage', 'cell_voltage', 'pack_voltage'],
    'current': ['current', 'pack_current', 'cell_current'],
    'temperature': ['temperature', 'cell_temperature', 'cell_temp', 'temp', 'ambient_temp'],
    'soc': ['soc', 'state_of_charge', 'state_of_charge_%', 'soc_pct'],
    'dod': ['dod', 'depth_of_discharge', 'depth_of_discharge_%', 'dod_pct'],
    'cycle_number': ['cycle', 'cycle_number', 'cycle_id', 'cycle_no'],
    'c_rate': ['c_rate', 'c-rate', 'c rate', 'charge_rate'],
    'capacity_remaining': ['capacity', 'capacity_remaining', 'cap_rem', 'cap_%', 'capacity_pct', 'soh_pct', 'soh'],
    'rul': ['rul', 'rul_cycles', 'remaining_useful_life', 'remaining_life'],
}

REQUIRED_FEATURES = list(COLUMN_ALIASES.keys())


def _find_column(df_cols: List[str], aliases: List[str]) -> str:
    lower_cols = {c.lower(): c for c in df_cols}
    for alias in aliases:
        if alias.lower() in lower_cols:
            return lower_cols[alias.lower()]
    # best partial match
    for alias in aliases:
        for c in df_cols:
            if alias.lower() in c.lower() or c.lower() in alias.lower():
                return c
    return ''


def map_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str], List[str]]:
    mapping: Dict[str, str] = {}
    missing: List[str] = []
    for key, aliases in COLUMN_ALIASES.items():
        col = _find_column(list(df.columns), aliases)
        if col:
            mapping[key] = col
        else:
            missing.append(key)

    mapped_df = df.copy()
    for key, col in mapping.items():
        mapped_df[key] = mapped_df[col]

    return mapped_df, mapping, missing


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df


def load_and_map(path: str):
    df = load_csv(path)
    df_out, mapping, missing = map_columns(df)
    return df_out, mapping, missing
