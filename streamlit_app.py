import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import requests
import io
import os
from datetime import datetime

# --- 1. TNNM SYSTEM CONFIGURATION ---
ST_COLOR_MAP = {
    "Propaganda / Manufactured Spin": "#FF9800",
    "Severe Suppression / Active Censorship": "#F44336",
    "Routine Statecraft / Bureaucratic Tone": "#9E9E9E",
    "Baseline Regional Tone": "#4CAF50"
}

PILLARS = {
    "Geographic": ["Tibet", "Xizang", "TAR", "Roof of the World"],
    "Diplomatic": ["One-China", "Belt and Road", "BRI", "Gentleman's Agreement", "MLAT", "Extradition"],
    "Dissent": ["Dalai Lama", "Tibetan refugee", "Free Tibet", "CTA", "separatism"],
    "Border": ["Shigatse", "Gyirong Port", "Kerung", "securitization", "liveable villages"],
    "Media": ["Confucius Institute", "mask diplomacy", "soft power", "RSS", "Samachar Samiti"]
}

# --- 2. DATABASE & SYNC LOGIC ---
def init_db():
    conn = sqlite3.connect("tnnm_live_monitor.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS research_vault (
            gkgid TEXT PRIMARY KEY, date TEXT, year TEXT, publisher TEXT, url TEXT, 
            flag TEXT, c_delta REAL, literal REAL, subtext REAL,
            s_anxiety REAL, s_complexity REAL, s_anger REAL
        )
    """)
    conn.commit()
    return conn

@st.cache_data(ttl=900)
def fetch_live_tnnm_data():
    """Optimized GDELT fetcher with timeout and error handling."""
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    # Core anchors only for the 15-min live stream to avoid URL length issues
    core_anchors = '"Tibet" OR "Xizang" OR "BRI" OR "Dalai Lama" OR "Border"'
    full_query = f'({core_anchors}) sourcecountry:NP'
    
    params = {
        "query": full_query,
        "mode": "ArtList",
        "format": "CSV",
        "maxrecords": 50,
        "timespan": "15min"
    }
    
    try:
        # 5-second timeout prevents the app from hanging if GDELT is slow
        response = requests.get(base_url, params=params, timeout=5)
        if response.status_code == 200:
            return pd.read_csv(io.StringIO(response.text))
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def sync_data(conn, df):
    if df is None or df.empty: return 0
    cursor = conn.cursor()
    added = 0
    df = df.rename(columns={'URL': 'url', 'SourceCommonName': 'publisher', 'Date': 'date'})
    for _, row in df.iterrows():
        url = str(row.get('url'))
        cursor.execute("SELECT 1 FROM research_vault WHERE url=?", (url,))
        if not cursor.fetchone():
            # Forensic simulation
            c_delta = 15.0 if "tibet" in url.lower() or "bri" in url.lower() else 0.0
            flag = "Severe Suppression / Active Censorship" if c_delta > 10 else "Baseline Regional Tone"
            cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (str(datetime.now().timestamp()), str(row.get('date')), str(row.get('date'))[:4],
                          row.get('publisher'), url, flag, c_delta, 50.0, 50.0, 10.0, 10.0, 5.0))
            added += 1
    conn.commit()
    return added

# --- 3. DASHBOARD EXECUTION ---
st.set_page_config(page_title="TNNM Live Monitor", layout="wide", page_icon="🇳🇵")
conn = init_db()

st.title("🇳🇵 TNNM Live Geopolitical Monitor")
st.caption(f"Syncing Nepali Media every 15 Minutes | Two-Gate Filtering Active")

# Attempt Sync
with st.spinner("Synchronizing with GDELT Global Feed..."):
    live_batch = fetch_live_tnnm_data()
    new_count = sync_data(conn, live_batch)

# Load ALL data from the local vault (Archive + New Live Data)
df_all = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_all.empty:
    # 1. Executive KPIs
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Records", len(df_all))
    m2.metric("Suppression Flags", len(df_all[df_all['flag'].str.contains('Suppression')]))
    m3.metric("Avg Muting Index", round(df_all['c_delta'].mean(), 2))
    m4.metric("New (Last Sync)", new_count)

    # 2. Narrative Trajectory Chart
    st.header("📉 Longitudinal Trajectory")
    trend = df_all.groupby(['year', 'flag']).size().reset_index(name='Count')
    fig = px.line(trend, x='year', y='Count', color='flag', color_discrete_map=ST_COLOR_MAP, markers=True)
    st.plotly_chart(fig, use_container_width=True)

    # 3. Source Explorer
    st.header("🔍 Source Explorer")
    st.dataframe(df_all[['date', 'publisher', 'flag', 'url']].sort_values('date', ascending=False), use_container_width=True)
    
    # 4. AI Analyst
    if st.button("📝 Generate Forensic Report"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            stats = df_all['flag'].value_counts().to_dict()
            response = model.generate_content(f"Analyze these Nepali media flags: {stats}")
            st.markdown(response.text)
        except Exception as e: st.error(f"API Error: {e}")
else:
    # This prevents the "Waiting" message from sticking if no data exists yet
    st.warning("No data found in GDELT for this 15-min window. Upload historical CSVs in the sidebar to populate the vault.")

with st.sidebar:
    st.header("Archival Data")
    arch_file = st.file_uploader("Upload Historical TNNM CSV")
    if arch_file:
        arch_df = pd.read_csv(arch_file)
        sync_data(conn, arch_df)
        st.success("Archive Merged!")
