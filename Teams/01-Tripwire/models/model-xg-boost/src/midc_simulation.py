import numpy as np
import pandas as pd


def generate_midc_profile():
    time_s = np.array([0,10,20,30,40,50,60,70,90,110,130,150,170,200,230,260,300,340,380,420,460,500,540,580,620,660,700,760,820,880,940,1000,1060,1080], dtype=float)
    speed_kmh = np.array([0,10,20,30,35,30,25,0,15,30,40,50,45,35,25,10,0,20,35,45,55,60,55,45,35,20,0,20,35,50,60,40,20,0], dtype=float)
    speed_ms = speed_kmh * 1000 / 3600
    accel = np.gradient(speed_ms, time_s)
    return pd.DataFrame({'time_s': time_s, 'speed_kmh': speed_kmh, 'speed_ms': speed_ms, 'accel': accel})


def simulate_midc_drive(vehicle_mass=2500.0,
                        rolling_resistance=0.015,
                        drag_coefficient=0.32,
                        frontal_area=2.5,
                        air_density=1.225,
                        motor_efficiency=0.90,
                        nominal_voltage=350.0,
                        regen_efficiency=0.55):
    cycle = generate_midc_profile()
    g = 9.81
    F_roll = vehicle_mass * g * rolling_resistance
    F_drag = 0.5 * air_density * drag_coefficient * frontal_area * cycle['speed_ms'] ** 2
    F_accel = vehicle_mass * cycle['accel']
    F_total = F_roll + F_drag + np.maximum(F_accel, 0)
    P = F_total * cycle['speed_ms']
    regen_force = np.minimum(F_accel, 0)
    P_regen = np.minimum(regen_force * cycle['speed_ms'] * regen_efficiency, 0)
    P_battery = np.maximum(P / motor_efficiency + P_regen, 0)
    dt = np.gradient(cycle['time_s'])
    energy_joules = np.sum(P_battery * dt)
    energy_kwh = energy_joules / 3.6e6
    avg_power_kw = np.mean(P_battery) / 1000.0
    avg_current = np.mean(P_battery / nominal_voltage)
    dt = np.diff(cycle['time_s'], append=cycle['time_s'].iloc[-1])
    avg_speed_kmh = np.sum(cycle['speed_ms'] * dt) / np.sum(dt) * 3.6 if np.sum(dt) > 0 else 0
    distance_km = np.sum(cycle['speed_ms'] * dt) / 1000.0

    return {
        'energy_kwh': energy_kwh,
        'avg_power_kw': avg_power_kw,
        'avg_current': avg_current,
        'avg_voltage': nominal_voltage,
        'avg_speed_kmh': avg_speed_kmh,
        'distance_km': distance_km,
        'speed_series': cycle[['time_s', 'speed_kmh', 'speed_ms']],
        'power_series_kw': P_battery / 1000.0,
    }


if __name__ == '__main__':
    out = simulate_midc_drive()
    print(f"MIDC drive: {out['distance_km']:.2f} km, {out['energy_kwh']:.3f} kWh consumed, avg speed {out['avg_speed_kmh']:.2f} km/h")
