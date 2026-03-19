import numpy as np
import plotly.express as px
import plotly.graph_objects as go

def plot_capacity_curve(df):
    return px.line(df, x='cycle_number', y='capacity_remaining', title='Capacity fade over cycles')

def plot_soc_curve(df):
    if 'soc' in df.columns:
        return px.line(df, x='cycle_number', y='soc', title='SOC trend')
    return px.line(df, x='cycle_number', y='soc_start', title='SOC start trend')

def plot_temp_exposure(df):
    return px.line(df, x='cycle_number', y='temperature', title='Temperature exposure')

def plot_midc_speed(df):
    if 'speed_series' in df.columns:
        row = df.iloc[-1]
        speed_series = row['speed_series']
        return px.line(speed_series, x='time_s', y='speed_kmh', title='MIDC speed profile')
    return go.Figure()

def plot_power_vs_time(df):
    if 'power_series_kw' in df.columns:
        row=df.iloc[-1]
        ps=row['power_series_kw']
        return px.line(x=np.arange(len(ps)), y=ps, labels={'x':'time step','y':'Battery Power (kW)'}, title='Battery power vs time')
    return go.Figure()

def plot_soc_time(df):
    if 'soc_series' in df.columns:
        row=df.iloc[-1]
        ss=row['soc_series']
        return px.line(ss, x='time_s', y='soc', title='SOC vs time')
    return go.Figure()

def plot_degradation_trend(df):
    return px.scatter(df, x='cycle_number', y='capacity_remaining', color='temperature', title='Capacity fade with temperature')

def plot_dod_vs_degradation(df):
    return px.scatter(df, x='dod', y='capacity_remaining', color='temperature', title='DoD vs degradation')

