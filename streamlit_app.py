import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import requests
import io
from datetime import datetime

# --- 1. NEPAL-ONLY SOURCE FILTERING ---
# GDELT Source Country code for Nepal is 'NP'
def is_nepali_source(url, publisher):
    """Filters for Nepali domains or known Nepali media publishers."""
    nepali_domains = ['.np', 'onlinekhabar.com', 'ratopati.com', 'setopati.com', 
                      'kathmandupost.com', 'myrepublica.nagariknetwork.com', 
                      'thehimalayantimes.com', 'nepalitimes.com', 'ekantipur.com',
                      'gorkhapatraonline.com', 'risingnepaldaily.com', 'annapurnapost.com']
    
    url_lower = str(url).lower()
    pub_lower = str(publisher).lower()
    
    return any(domain in url_lower for domain in nepali_domains) or \
           any(domain in pub_lower for domain in nepali_domains)

# --- 2. AUTOMATED GDELT FETCH (STRICTLY NEPAL) ---
@st.cache_data(ttl=900)
def fetch_live_nepal_data(search_query):
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    # 'sourcecountry:NP' ensures only Nepali registered sources are returned
    query = f'({search_query}) sourcecountry:NP'
    
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "CSV",
        "maxrecords": 100,
        "sort": "DateDesc"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=20)
        if response.status_code == 200:
            return pd.read_csv(io.StringIO(response.text))
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# --- 3. DATABASE & PERSISTENCE ---
def init_db():
    conn = sqlite3.connect("nepal_influence_final.db", check_same_thread=False)
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

def sync_data(conn, df, source_type="Live"):
    cursor = conn.cursor()
    added = 0
    # Mapping GDELT API & CSV headers
    col_map = {'URL': 'url', 'SourceCommonName': 'publisher', 'Date': 'date', 
               'GKGRECORDID': 'gkgid', 'V2Themes': 'themes', 'GCAM': 'gcam'}
    df = df.rename(columns=col_map)
    
    sensitive = ['rights', 'refugee', 'dalai', 'cta', 'dispute', 'arrest', 'border']

    for _, row in df.iterrows():
        url = str(row.get('url', ''))
        pub = str(row.get('publisher', ''))
        
        # STRICT NEPAL FILTER: Skip if not a Nepali source
        if not is_nepali_source(url, pub):
            continue
            
        gkgid = str(row.get('gkgid', str(row.get('date', '')) + str(hash(url))[:6]))
        
        cursor.execute("SELECT 1 FROM research_vault WHERE url=?", (url,))
        if not cursor.fetchone():
            text = (url + " " + str(row.get('themes', ''))).lower()
            rel = 1 if any(k in text for k in ['tibet', 'xizang', 'buddhism']) else 0
            amp = 1 if rel and any(k in text for k in ['bri', 'development', 'harmony']) else 0
            res = 1 if rel and any(k in text for k in sensitive) else 0
            
            try:
                parts = str(row.get('gcam', '0,0,0')).split(',')
                tone, anx = float(parts[0]), float(parts[2])
            except: tone, anx = 0.0, 0.0

            cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (gkgid, str(row.get('date'))[:8], str(row.get('date'))[:4], 
                          pub, url, str(row.get('themes')), str(row.get('gcam')), tone, anx, amp, res, 0, rel))
            added += 1
    conn.commit()
    return added

# --- 4. DASHBOARD UI ---
st.set_page_config(page_title="Nepal Media influence Monitor", layout="wide")
conn = init_db()

st.title("🇳🇵 Nepal-Only Media Influence Analyzer")
st.caption(f"Status: Monitoring Nepali Digital Information Space | Last Sync: {datetime.now().strftime('%H:%M:%S')}")

with st.sidebar:
    st.header("1. Live Monitoring")
    live_keywords = st.text_input("Keywords (NP Sources Only)", "Tibet, Xizang, Buddhism")
    st.caption("Auto-refreshes every 15 minutes.")
    
    st.header("2. Archival Upload")
    archives = st.file_uploader("Upload Historical CSV/Excel", accept_multiple_files=True)
    if st.button("Process Archives"):
        if archives:
            for f in archives:
                df_arch = pd.read_csv(f) if f.name.endswith('.csv') else pd.read_excel(f)
                count = sync_data(conn, df_arch, "Archive")
                st.success(f"Processed {f.name}: {count} Nepali articles added.")

# --- 5. EXECUTION & VISUALIZATION ---
# A. Fetch Live Data
live_df = fetch_live_nepal_data(live_keywords)
if not live_df.empty:
    sync_data(conn, live_df)

# B. Load Visuals
df_all = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_all.empty:
    # Keyword Frequency Analysis
    keywords = [k.strip().lower() for k in live_keywords.split(",") if k.strip()]
    kw_data = [{"Keyword": kw.upper(), "Frequency": (df_all['url'].str.contains(kw, case=False).sum())} for kw in keywords]
    
    st.header("📊 Nepali Media Keyword Frequency")
    st.plotly_chart(px.bar(pd.DataFrame(kw_data), x="Keyword", y="Frequency", color="Keyword"))

    # Trajectory
    st.header("📉 Longitudinal Trajectory (2015-2025)")
    trend = df_all.groupby(['year', 'publisher']).size().reset_index(name='Articles')
    st.plotly_chart(px.line(trend, x='year', y='Articles', color='publisher', markers=True))

    # Source Explorer
    st.header("🔍 Nepali Source Archive")
    st.dataframe(df_all[['year', 'publisher', 'url', 'tone']].sort_values('year', ascending=False), 
                 use_container_width=True, column_config={"url": st.column_config.LinkColumn()})

    # AI Analysis Detail
    if st.button("📝 Generate Detailed Analysis"):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        top_pubs = df_all['publisher'].value_counts().head(5).to_string()
        response = model.generate_content(f"Analyze the narrative trajectory of these top Nepali sources: {top_pubs}. Query: {live_keywords}")
        st.markdown(response.text)
else:
    st.info("Awaiting Nepali media data. Enter keywords or upload archives.")
