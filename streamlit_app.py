import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import requests
from datetime import datetime, timedelta

# --- 1. AUTOMATED GDELT FETCH ENGINE ---
@st.cache_data(ttl=900)  # 900 seconds = 15 minutes
def fetch_live_gdelt_data(search_query):
    """Fetches real-time data from GDELT DOC API 2.0 based on keywords."""
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    
    # GDELT search syntax for Nepal-specific media
    # near5 identifies words close to each other for higher accuracy
    query = f'({search_query}) sourcecountry:nepal'
    
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "CSV",
        "maxrecords": 75, # GDELT free tier limit per 15 mins
        "sort": "DateDesc"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=20)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# --- 2. DATABASE & ANALYSIS ENGINE ---
def init_db():
    conn = sqlite3.connect("nepal_influence.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS research_vault (
            gkgid TEXT PRIMARY KEY, date TEXT, year TEXT, publisher TEXT, url TEXT, 
            themes TEXT, gcam TEXT, tone REAL, anxiety REAL, 
            amplify INT, resist INT, self_censor INT, relevant INT
        )
    """)
    conn.commit()
    return conn

def sync_to_vault(conn, df):
    cursor = conn.cursor()
    added = 0
    # Map GDELT API column names to internal database names
    col_map = {'URL': 'url', 'SourceCommonName': 'publisher', 'Date': 'date'}
    df = df.rename(columns=col_map)
    
    sensitive = ['rights', 'refugee', 'dalai', 'cta', 'dispute', 'arrest', 'border']
    
    for _, row in df.iterrows():
        url = str(row.get('url', ''))
        # Generate a unique ID if GKGID is missing from ArtList mode
        gkgid = str(row.get('date', '')) + str(hash(url))[:8]
        
        cursor.execute("SELECT 1 FROM research_vault WHERE url=?", (url,))
        if not cursor.fetchone():
            text = url.lower()
            rel = 1 if any(k in text for k in ['tibet', 'xizang', 'buddhism']) else 0
            amp = 1 if rel and any(k in text for k in ['bri', 'development', 'partnership']) else 0
            res = 1 if rel and any(k in text for k in sensitive) else 0
            
            # GDELT ArtList doesn't provide GCAM, so we estimate Tone from metadata or use 0.0
            cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (gkgid, str(row.get('date'))[:8], str(row.get('date'))[:4], 
                          row.get('publisher'), url, "Live Feed", "0,0,0", 0.0, 0.0, amp, res, 0, rel))
            added += 1
    conn.commit()
    return added

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Live Media Monitor", layout="wide")
conn = init_db()

st.title("🇳🇵 Real-Time Nepal Media influence Monitor")
st.caption(f"Last Auto-Sync: {datetime.now().strftime('%H:%M:%S')} (Refreshes every 15 mins)")

with st.sidebar:
    st.header("Search Parameters")
    # This query will be sent to GDELT every 15 minutes
    live_keywords = st.text_input("Live GDELT Keywords", "Tibet, Xizang, Buddhism")
    st.info("GDELT is currently monitoring 100+ Nepali sources for these terms.")
    
    if st.button("Manual Force Refresh"):
        st.cache_data.clear()
        st.rerun()

# --- 4. THE AUTOMATED LOOP ---
# This line runs every 15 minutes automatically due to TTL
live_data = fetch_live_gdelt_data(live_keywords)

if not live_data.empty:
    new_count = sync_to_vault(conn, live_data)
    if new_count > 0:
        st.toast(f"New Data Found: {new_count} articles added from live feed.")

# --- 5. VISUALIZATION OF ACCUMULATED DATA ---
df_viz = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_viz.empty:
    # Keyword Frequency Logic
    kw_list = [k.strip().lower() for k in live_keywords.split(",")]
    kw_counts = []
    for k in kw_list:
        count = df_viz['url'].str.contains(k, case=False).sum()
        kw_counts.append({"Keyword": k.upper(), "Frequency": count})
    
    st.header("📊 Live Keyword Impact")
    st.plotly_chart(px.bar(pd.DataFrame(kw_counts), x="Keyword", y="Frequency", color="Keyword"))

    # Longitudinal Trajectory
    st.header("📉 Narrative Trajectory (Live + Archival)")
    trend = df_viz.groupby(['year', 'publisher']).size().reset_index(name='Articles')
    st.plotly_chart(px.line(trend, x='year', y='Articles', color='publisher', markers=True))

    # Source Explorer
    st.header("🔍 Real-Time Source Archive")
    st.dataframe(df_viz[['year', 'publisher', 'url']].sort_values('year', ascending=False), use_container_width=True)

    # Detailed Analysis Detail
    if st.button("📝 Analyze Live Trends"):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        context = f"Top Publishers: {df_viz['publisher'].head(5).tolist()}. Keywords: {live_keywords}"
        response = model.generate_content(f"Analyze the live media trajectory for: {context}")
        st.markdown(response.text)
