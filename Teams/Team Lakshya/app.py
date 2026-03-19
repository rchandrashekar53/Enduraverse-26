import streamlit as st
import requests
import time
from supabase import create_client
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

# ===== SUPABASE CONFIG =====
SUPABASE_URL = "https://aerpmreyscpdcmzmuyfh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFlcnBtcmV5c2NwZGNtem11eWZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM4MzYzOTAsImV4cCI6MjA4OTQxMjM5MH0.E0L_e5okEoBsMqz6j6d5rMjHHr6KehX45FE5NRFMYnM"   # 🔐 keep your real key here
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===== PAGE CONFIG =====
st.set_page_config(page_title="Smart Monitoring", layout="wide")

# ===== SESSION CONTROL =====
if "last_upload" not in st.session_state:
    st.session_state.last_upload = 0

# ===== SIDEBAR =====
st.sidebar.title("⚙️ Control Panel")
threshold = st.sidebar.slider("Temperature Threshold", 30, 100, 50)
ai_mode = st.sidebar.selectbox("AI Mode", ["Basic", "Predictive", "Advanced"])
auto_upload = st.sidebar.toggle("Auto Upload", True)

# ===== UI STYLE =====
st.markdown("""
<style>
body { background-color: #0e1117; color: white; }
.stMetric { background-color: #1c1f26; padding: 15px; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

st.title("🔥 Smart Industrial Monitoring Dashboard")

# ===== AI MODEL =====
def train_window_model(history, window_size=5):
    if len(history) <= window_size:
        return None
    try:
        X, y = [], []
        for i in range(len(history) - window_size):
            X.append(history[i:i+window_size])
            y.append(history[i+window_size])
        X, y = np.array(X), np.array(y)

        model = LinearRegression()
        model.fit(X, y)

        last_window = np.array(history[-window_size:]).reshape(1, -1)
        return model.predict(last_window)[0]
    except:
        return None

def statistical_anomaly(temp, history):
    if len(history) < 5:
        return "OK"
    mean, std = np.mean(history), np.std(history)
    if std == 0:
        return "OK"
    z = abs((temp - mean) / std)
    return "NOK" if z > 2 else "OK"

def get_ai_risk(temp, predicted_temp):
    if predicted_temp is None:
        return "LOW", 0, "OK"
    deviation = abs(temp - predicted_temp)
    if deviation <= 2:
        return "LOW", deviation, "OK"
    elif deviation <= 4:
        return "MEDIUM", deviation, "WARNING"
    else:
        return "HIGH", deviation, "NOK"

def get_trend(history):
    if len(history) < 5:
        return "STABLE"
    recent = history[-5:]
    return "RISING" if recent[-1] > recent[0] else "FALLING" if recent[-1] < recent[0] else "STABLE"

# ===== LAYOUT =====
col1, col2 = st.columns(2)

# ===== CAMERA =====
with col1:
    st.subheader("📷 Live Camera")
    st.components.v1.iframe("http://10.220.100.250", height=400)

# ===== SENSOR =====
with col2:
    st.subheader("🌡️ Temperature")
    placeholder = st.empty()

    try:
        res = requests.get("http://10.220.100.192:5000/get-data", timeout=2)
        data = res.json()

        temp = data.get("temperature", 0)

        st.write("Temp:", temp)  # debug

        # ===== HISTORY =====
        history = []
        try:
            r = supabase.table("machine_data")\
                .select("temperature")\
                .order("id", desc=False)\
                .limit(50)\
                .execute()

            if r.data:
                history = [i["temperature"] for i in r.data]
        except:
            history = []

        # ===== AI =====
        predicted_temp = train_window_model(history)
        stat_status = statistical_anomaly(temp, history)
        risk_level, deviation, machine_state = get_ai_risk(temp, predicted_temp)
        trend = get_trend(history)

        # ===== STATUS =====
        if ai_mode == "Basic":
            status = "OK" if temp < threshold else "NOK"
        elif ai_mode == "Predictive":
            status = "OK" if machine_state != "NOK" else "NOK"
        else:
            status = "NOK" if (machine_state == "NOK" or stat_status == "NOK") else "OK"

        placeholder.metric("Temperature (°C)", temp)

        # ===== KPI =====
        k1, k2 = st.columns(2)
        k3, k4 = st.columns(2)
        k1.metric("Temp", temp)
        # Safe formatting
        pred_val = f"{predicted_temp:.2f}" if predicted_temp is not None else "--"
        risk_val = str(risk_level)
        trend_val = str(trend)

        k2.metric("Predicted", pred_val)
        k3.metric("Risk", risk_val)
        k4.metric("Trend", trend_val)

        # ===== STATUS DISPLAY =====
        if status == "OK":
            st.success("🟢 STATUS: OK")
        else:
            st.error("🔴 STATUS: NOK")

        # ===== AUTO UPLOAD (FIXED) =====
        if auto_upload and time.time() - st.session_state.last_upload > 10:
            try:
                data_packet = {
                    "temperature": float(temp),
                    "status": str(status),
                    "image_url": "ESP32_STREAM"
                }

                res = supabase.table("machine_data").insert(data_packet).execute()

                st.success(f"✅ Uploaded: {data_packet}")

                st.session_state.last_upload = time.time()

            except Exception as e:
                st.error(f"❌ Upload error: {e}")

    except Exception as e:
        placeholder.warning("⚠️ Waiting for data...")
        st.error(e)

# ===== CLOUD =====
st.subheader("☁️ Latest Cloud Record")

try:
    r = supabase.table("machine_data").select("*").order("id", desc=True).limit(1).execute()

    if r.data:
        latest = r.data[0]
        st.write(f"🌡️ Temp: {latest['temperature']} °C")
        st.write(f"📊 Status: {latest['status']}")
    else:
        st.warning("No data yet")

except Exception as e:
    st.error(f"Cloud error: {e}")

# ===== GRAPH =====
st.subheader("📈 Temperature Trend")

try:
    r = supabase.table("machine_data")\
        .select("temperature")\
        .order("id", desc=False)\
        .limit(50)\
        .execute()

    if r.data:
        df = pd.DataFrame(r.data)
        st.line_chart(df["temperature"])
    else:
        st.warning("No graph data")

except Exception as e:
    st.error(f"Graph error: {e}")

# ===== DEFECT ANALYSIS =====
st.subheader("⚠️ Defect Analysis")

try:
    r = supabase.table("machine_data").select("status").execute()

    if r.data:
        d = pd.DataFrame(r.data)

        ok_count = (d["status"] == "OK").sum()
        nok_count = (d["status"] == "NOK").sum()

        col1, col2 = st.columns(2)

        col1.metric("✅ OK", ok_count)
        col2.metric("❌ NOK", nok_count)

    else:
        st.warning("No data yet")

except Exception as e:
    st.error(f"Analysis error: {e}")

# ===== AUTO REFRESH =====
time.sleep(2)
st.rerun()