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

def sync_data(conn, df):
    if df is None or df.empty: return 0
    cursor = conn.cursor()
    added = 0
    
    # ROBUST MAPPING: Handles GDELT Live, TNNM Archive, and varying case sensitivity
    col_map = {
        'DocumentIdentifier': 'url', 'URL': 'url', 'url': 'url',
        'DATE': 'date', 'Date': 'date', 'date': 'date',
        'SourceCommonName': 'publisher', 'Publisher': 'publisher', 'publisher': 'publisher',
        'Editorial_Flag': 'flag', 'flag': 'flag',
        'Censorship_Delta': 'c_delta', 'c_delta': 'c_delta'
    }
    df = df.rename(columns=col_map)
    
    for _, row in df.iterrows():
        url = str(row.get('url', 'Unknown URL'))
        
        # Date & Year Fix (Prevents the 'None' issue from image_1bc83d.png)
        date_raw = str(row.get('date', ''))
        if date_raw == 'None' or date_raw == 'nan' or not date_raw:
            date_val = datetime.now().strftime('%Y-%m-%d')
        else:
            date_val = date_raw
            
        year_val = date_val[:4] if len(date_val) >= 4 else datetime.now().strftime('%Y')
        
        cursor.execute("SELECT 1 FROM research_vault WHERE url=?", (url,))
        if not cursor.fetchone():
            flag = row.get('flag', 'Baseline Regional Tone')
            c_delta = float(row.get('c_delta', 0.0))
            
            # Simple Forensic Heuristic for new live entries
            if flag == 'Baseline Regional Tone' and any(k.lower() in url.lower() for p in PILLARS.values() for k in p):
                if "tibet" in url.lower() or "bri" in url.lower():
                    c_delta = 12.0
                    flag = "Severe Suppression / Active Censorship"
            
            cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (str(datetime.now().timestamp()), date_val, year_val,
                          row.get('publisher', 'Unknown'), url, flag, c_delta, 
                          row.get('literal', 50.0), row.get('subtext', 50.0), 10.0, 10.0, 5.0))
            added += 1
    conn.commit()
    return added

@st.cache_data(ttl=900)
def fetch_live_tnnm_data():
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    core_anchors = '"Tibet" OR "Xizang" OR "BRI" OR "Dalai Lama" OR "Border"'
    params = {"query": f'({core_anchors}) sourcecountry:NP', "mode": "ArtList", "format": "CSV", "maxrecords": 50, "timespan": "15min"}
    try:
        response = requests.get(base_url, params=params, timeout=5)
        if response.status_code == 200:
            return pd.read_csv(io.StringIO(response.text))
    except:
        pass
    return pd.DataFrame()

# --- 3. DASHBOARD EXECUTION ---
st.set_page_config(page_title="TNNM Live Monitor", layout="wide", page_icon="🇳🇵")
conn = init_db()

# SIDEBAR: Process Uploads first to ensure they are available for the current run
with st.sidebar:
    st.header("Archival Data")
    arch_file = st.file_uploader("Upload Historical TNNM CSV", type=['csv'])
    if arch_file:
        temp_df = pd.read_csv(arch_file)
        sync_data(conn, temp_df)
        st.success("Archive Merged!")
        st.rerun()

st.title("🇳🇵 TNNM Live Geopolitical Monitor")
st.caption(f"Syncing Nepali Media every 15 Minutes | Two-Gate Filtering Active")

# Silent Background Live Sync
live_batch = fetch_live_tnnm_data()
new_count = sync_data(conn, live_batch)

# Main Data Load from Vault
df_all = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_all.empty:
    # 1. Executive KPIs
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Records", len(df_all))
    m2.metric("Suppression Flags", len(df_all[df_all['flag'].str.contains('Suppression', na=False)]))
    m3.metric("Avg Muting Index", round(df_all['c_delta'].mean(), 2))
    m4.metric("Live Sync (New)", new_count)

    # 2. Longitudinal Trajectory Chart
    st.header("📉 Longitudinal Trajectory")
    df_all['year'] = df_all['year'].fillna('Unknown')
    # Filter out 'None' or 'nan' years for cleaner plotting
    plot_df = df_all[df_all['year'].str.len() == 4]
    trend = plot_df.groupby(['year', 'flag']).size().reset_index(name='Count')
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
            response = model.generate_content(f"Analyze the following Nepali media distribution: {stats}. Focus on active censorship trends.")
            st.markdown(response.text)
        except Exception as e: st.error(f"API Error: {e}")
else:
    st.warning("Vault is empty. Please upload 'TNNM_Geopolitical_Corpus_Final.csv' in the sidebar to populate the monitor.")
