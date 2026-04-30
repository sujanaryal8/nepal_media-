import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import requests
import io
from datetime import datetime

# --- 1. TNNM SYSTEM CONFIGURATION ---
ST_COLOR_MAP = {
    "Propaganda / Manufactured Spin": "#FF9800",
    "Severe Suppression / Active Censorship": "#F44336",
    "Routine Statecraft / Bureaucratic Tone": "#9E9E9E",
    "Baseline Regional Tone": "#4CAF50"
}

# --- 2. DATABASE & ETL ENGINE ---
def init_db():
    conn = sqlite3.connect("tnnm_geopolitical.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS research_vault (
            gkgid TEXT PRIMARY KEY, date TEXT, year TEXT, publisher TEXT, url TEXT, 
            keywords TEXT, flag TEXT, c_delta REAL, literal REAL, subtext REAL,
            s_anger REAL, s_anxiety REAL, s_complexity REAL, s_tentative REAL, s_actref REAL
        )
    """)
    conn.commit()
    return conn

def sync_to_vault(conn, df):
    cursor = conn.cursor()
    added = 0
    # Mapping for TNNM Schema and GDELT Fallbacks
    col_map = {
        'GKGRECORDID': 'gkgid', 'DATE': 'date', 'SourceCommonName': 'publisher', 
        'DocumentIdentifier': 'url', 'Dashboard_Keywords': 'keywords', 
        'Editorial_Flag': 'flag', 'Censorship_Delta': 'c_delta',
        'Literal_Text_Score': 'literal', 'Subtext_Gravity_Score': 'subtext'
    }
    df = df.rename(columns=col_map)

    for _, row in df.iterrows():
        gkgid = str(row.get('gkgid', hash(str(row.get('url')))))
        cursor.execute("SELECT 1 FROM research_vault WHERE gkgid=?", (gkgid,))
        if not cursor.fetchone():
            # Ensure we handle forensic metrics even if missing in raw feed
            cursor.execute("""INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (gkgid, str(row.get('date')), str(row.get('date'))[:4], row.get('publisher'), 
                 row.get('url'), row.get('keywords'), row.get('flag', 'Baseline Regional Tone'),
                 row.get('c_delta', 0.0), row.get('literal', 0.0), row.get('subtext', 0.0),
                 row.get('S_Anger', 0.0), row.get('S_Anxiety', 0.0), row.get('S_Complexity', 0.0),
                 row.get('S_Tentative', 0.0), row.get('S_ActRef', 0.0)))
            added += 1
    conn.commit()
    return added

# --- 3. LIVE GDELT AUTOMATION (15 MIN TTL) ---
@st.cache_data(ttl=900)
def fetch_live_tnnm_feed(query):
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    full_query = f'({query}) sourcecountry:NP'
    params = {"query": full_query, "mode": "ArtList", "format": "CSV", "maxrecords": 50}
    try:
        res = requests.get(base_url, params=params, timeout=15)
        if res.status_code == 200:
            return pd.read_csv(io.StringIO(res.text))
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# --- 4. DASHBOARD UI ---
st.set_page_config(page_title="TNNM Forensic Monitor", layout="wide")
conn = init_db()

st.title("🇳🇵 TNNM Geopolitical & Forensic Monitor")
st.caption(f"Pipeline: ETL & NLP/GCAM Scoring | Sync Status: Live (15m Interval)")

with st.sidebar:
    st.header("1. Data Ingestion")
    files = st.file_uploader("Upload TNNM_Geopolitical_Corpus_Final.csv", accept_multiple_files=True)
    if st.button("Sync Archives"):
        if files:
            for f in files:
                df_load = pd.read_csv(f) if f.name.endswith('.csv') else pd.read_excel(f)
                count = sync_to_vault(conn, df_load)
                st.success(f"Merged {count} records from {f.name}")

    st.divider()
    st.header("2. Live Search")
    live_q = st.text_input("Active Keywords (comma-separated)", "Tibet, BRI, Xizang")

# Auto-sync live feed
live_df = fetch_live_tnnm_feed(live_q)
if not live_df.empty:
    sync_to_vault(conn, live_df)

# --- 5. VISUALIZATION ENGINE ---
df_all = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_all.empty:
    # Filter by search keywords (OR logic)
    keywords = [k.strip().lower() for k in live_q.split(",")]
    df_viz = df_all[df_all.apply(lambda r: any(kw in (str(r['url'])+str(r['keywords'])).lower() for kw in keywords), axis=1)]

    # Executive Stats
    st.header("📊 Executive Analysis")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Corpus Size", len(df_viz))
    c2.metric("Avg Censorship Delta", round(df_viz['c_delta'].mean(), 2))
    c3.metric("Suppression Intensity", len(df_viz[df_viz['flag'].str.contains('Suppression')]))
    c4.metric("Propaganda Count", len(df_viz[df_viz['flag'].str.contains('Propaganda')]))

    # Keyword Count (Your Requirement)
    st.subheader("Keyword Distribution")
    kw_counts = [{"Keyword": k.upper(), "Count": df_viz['url'].str.contains(k, case=False).sum()} for k in keywords]
    st.plotly_chart(px.bar(pd.DataFrame(kw_counts), x="Keyword", y="Count", color="Keyword"))

    # Longitudinal Trajectory
    st.header("📉 Longitudinal Trajectory")
    trend = df_viz.groupby(['year', 'flag']).size().reset_index(name='Articles')
    st.plotly_chart(px.line(trend, x='year', y='Articles', color='flag', markers=True, color_discrete_map=ST_COLOR_MAP))

    # Forensic Scatter
    st.header("🎭 Forensic Sentiment Mapping")
    st.plotly_chart(px.scatter(df_viz, x="literal", y="subtext", color="flag", 
                               hover_data=['publisher'], color_discrete_map=ST_COLOR_MAP))

    # Source Explorer
    st.header("🔍 Source Archive")
    st.dataframe(df_viz[['year', 'publisher', 'flag', 'url', 'c_delta']].sort_values('year', ascending=False), use_container_width=True)

    # --- 6. VISION-PROXY AI ANALYST (Fixed Repetitive Analysis) ---
    st.divider()
    st.header("🧬 Detailed Forensic Research Breakdown")
    if st.button("Generate Chart-Specific Intelligence Report"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            
            # Extract data-driven observations for the AI
            corr = df_viz['s_anxiety'].corr(df_viz['c_delta'])
            top_censor = df_viz[df_viz['flag'].str.contains('Suppression')]['publisher'].value_counts().head(2).to_dict()
            recent_trend = df_viz.groupby('year')['flag'].value_counts().unstack().tail(3).to_dict()
            
            prompt = f"""
            Analyze these specific chart findings for a Geopolitical Report:
            1. TRAJECTORY TRENDS: {recent_trend}
            2. PSYCHOLINGUISTIC CORRELATION (Anxiety/Censorship): {round(corr, 2)}
            3. TARGET PUBLISHERS: {top_censor}
            4. KEYWORD VOLUME: {kw_counts}
            
            Based ONLY on these numbers:
            - Explain the significance of the {round(corr, 2)} correlation in terms of Nepali self-censorship.
            - Interpret why specific keywords are triggering more 'Suppression' flags than 'Propaganda'.
            - Provide a forecast based on the 3-year trajectory data.
            """
            
            with st.spinner("Analyzing current chart data..."):
                st.markdown(model.generate_content(prompt).text)
        except Exception as e:
            st.error(f"API Error: {e}")
else:
    st.info("Awaiting TNNM data sync...")
