import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import requests
import io
from datetime import datetime

# --- 1. TNNM SYSTEM CONFIGURATION & PILLARS ---
ST_COLOR_MAP = {
    "Propaganda / Manufactured Spin": "#FF9800",
    "Severe Suppression / Active Censorship": "#F44336",
    "Routine Statecraft / Bureaucratic Tone": "#9E9E9E",
    "Baseline Regional Tone": "#4CAF50"
}

# Your Specific Keywords and Exclusions (Gate 1 & Gate 2)
PILLARS = {
    "Geographic": ["Tibet", "Xizang", "TAR", "Roof of the World"],
    "Diplomatic": ["One-China", "Belt and Road", "BRI", "Gentleman's Agreement", "MLAT", "Extradition"],
    "Dissent": ["Dalai Lama", "Tibetan refugee", "Free Tibet", "CTA", "separatism"],
    "Border": ["Shigatse", "Gyirong Port", "Kerung", "securitization", "liveable villages"],
    "Media": ["Confucius Institute", "mask diplomacy", "soft power", "RSS", "Samachar Samiti"]
}

# Negative Exclusions (The "NOT" Gate)
EXCLUSIONS = ["spiritual tourism", "monastery tour", "Everest expedition", "Kailash", "weather", "snowfall", "landslide"]

# --- 2. AUTOMATED GDELT GKG FETCH (15-MIN INTERVAL) ---
@st.cache_data(ttl=900)
def fetch_live_tnnm_data():
    """Pings GDELT DOC API with your specific Two-Gate Filter."""
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    
    # Construct Boolean Query
    include_q = " OR ".join([f'"{k}"' for p in PILLARS.values() for k in p])
    exclude_q = " ".join([f'-"{e}"' for e in EXCLUSIONS])
    full_query = f"({include_q}) {exclude_q} sourcecountry:NP"
    
    params = {
        "query": full_query,
        "mode": "ArtList",
        "format": "CSV",
        "maxrecords": 75,
        "timespan": "15min"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=20)
        return pd.read_csv(io.StringIO(response.text)) if response.status_code == 200 else pd.DataFrame()
    except:
        return pd.DataFrame()

# --- 3. DATABASE & FORENSIC SCORING ---
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
    cursor = conn.cursor()
    added = 0
    # Map GDELT to TNNM Schema
    col_map = {'URL': 'url', 'SourceCommonName': 'publisher', 'Date': 'date'}
    df = df.rename(columns=col_map)

    for _, row in df.iterrows():
        url = str(row.get('url'))
        cursor.execute("SELECT 1 FROM research_vault WHERE url=?", (url,))
        if not cursor.fetchone():
            # Scoring Logic: This simulates the Forensic Engine on live data
            c_delta = 15.0 if any(k in url.lower() for k in PILLARS["Dissent"]) else 0.0
            flag = "Severe Suppression / Active Censorship" if c_delta > 10 else "Baseline Regional Tone"
            
            cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (str(datetime.now().timestamp()), str(row.get('date')), str(row.get('date'))[:4],
                          row.get('publisher'), url, flag, c_delta, 50.0, 50.0, 10.0, 10.0, 5.0))
            added += 1
    conn.commit()
    return added

# --- 4. DASHBOARD UI ---
st.set_page_config(page_title="TNNM Live Monitor", layout="wide")
conn = init_db()

st.title("🇳🇵 TNNM Live Geopolitical Monitor")
st.caption(f"Syncing Nepali Media every 15 Minutes | Active Two-Gate Filtering")

# Background Sync
live_batch = fetch_live_tnnm_data()
if not live_batch.empty:
    sync_data(conn, live_batch)

df_all = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_all.empty:
    # Tier 1: Executive View
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Archive", len(df_all))
    m2.metric("Suppression Intensity", len(df_all[df_all['flag'].str.contains('Suppression')]))
    m3.metric("Avg Censorship Delta", round(df_all['c_delta'].mean(), 2))
    m4.metric("Last Sync Count", len(live_batch))

    # Keyword Impact Analysis (The "Keyword Count" Requirement)
    st.header("📊 Keyword Impact Analysis")
    kw_hits = []
    for pillar, kws in PILLARS.items():
        count = df_all['url'].str.contains("|".join(kws), case=False).sum()
        kw_hits.append({"Pillar": pillar, "Articles": count})
    st.plotly_chart(px.bar(pd.DataFrame(kw_hits), x="Pillar", y="Articles", color="Pillar"))

    # Longitudinal Trajectory
    st.header("📉 Narrative Trajectory (2015-2026)")
    trend = df_all.groupby(['year', 'flag']).size().reset_index(name='Count')
    st.plotly_chart(px.line(trend, x='year', y='Count', color='flag', color_discrete_map=ST_COLOR_MAP, markers=True))

    # Tier 2 & 3: Source Archive & Download
    st.header("🔍 Intelligence Source Archive")
    csv = df_all.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export Forensic Dataset (CSV)", csv, "tnnm_export.csv")
    st.dataframe(df_all[['year', 'publisher', 'flag', 'url', 'c_delta']], use_container_width=True)

    # --- 5. VISION-PROXY AI ANALYST ---
    st.divider()
    if st.button("📝 Generate Detailed Geopolitical Analysis"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            
            # Data Context for the AI
            stats = {
                "correlation": df_all['s_anxiety'].corr(df_all['c_delta']),
                "top_keywords": kw_hits,
                "flags": df_all['flag'].value_counts().to_dict()
            }
            
            prompt = f"""
            Analyze these TNNM findings: {stats}. 
            Specifically interpret:
            1. Why {stats['flags'].get('Severe Suppression / Active Censorship', 0)} suppression articles are appearing.
            2. The relationship between keyword pillars and censorship flags.
            3. The trajectory of Nepali media alignment with PRC narratives based on current momentum.
            """
            
            with st.spinner("AI is triangulating live data..."):
                st.markdown(model.generate_content(prompt).text)
        except Exception as e: st.error(f"API Error: {e}")
else:
    st.info("Awaiting initial GDELT sync. This usually takes 30-60 seconds.")
