import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import io

# --- 1. CORE RESEARCH PILLARS (Based on your latest keywords) ---
PILLARS = {
    "Geographic Identity": ["tibet", "xizang", "tar", "roof of the world"],
    "Diplomatic & Legal": ["one-china", "bri", "belt and road", "extradition", "mlat", "gentleman's agreement"],
    "Dissent & Activism": ["dalai lama", "tibetan refugee", "free tibet", "cta", "separatism"],
    "Border & Infrastructure": ["shigatse", "gyirong", "kerung", "securitization", "liveable villages"],
    "Media & Influence": ["confucius institute", "soft power", "rss", "rastriya samachar samiti", "cyber security"]
}

# Exclusions to reduce noise
NOISE_FILTERS = ["monastery tour", "everest expedition", "weather warning", "snowfall", "landslide"]

# --- 2. DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect("nepal_influence_final.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS research_vault (
            gkgid TEXT PRIMARY KEY, date TEXT, year TEXT, publisher TEXT, url TEXT, 
            themes TEXT, gcam TEXT, tone REAL, anxiety REAL, pillar TEXT
        )
    """)
    conn.commit()
    return conn

def process_and_categorize(conn, files):
    cursor = conn.cursor()
    added = 0
    col_map = {'GKGRECORDID': 'gkgid', 'Publisher': 'publisher', 'SourceCommonName': 'publisher',
               'URL': 'url', 'DocumentIdentifier': 'url', 'Themes': 'themes', 'V2Themes': 'themes', 'GCAM': 'gcam'}

    for file in files:
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df = df.rename(columns=col_map)
        for _, row in df.iterrows():
            gkgid = str(row.get('gkgid', ''))
            if not gkgid or gkgid == 'nan': continue
            
            cursor.execute("SELECT 1 FROM research_vault WHERE gkgid=?", (gkgid,))
            if not cursor.fetchone():
                u, t = str(row.get('url', '')).lower(), str(row.get('themes', '')).lower()
                combined = u + " " + t
                
                # Apply Noise Filters
                if any(noise in combined for noise in NOISE_FILTERS):
                    continue
                
                # Categorize into Pillars
                assigned_pillar = "Other"
                for pillar, kws in PILLARS.items():
                    if any(k in combined for k in kws):
                        assigned_pillar = pillar
                        break
                
                if assigned_pillar == "Other": continue # Keep corpus high-density

                try:
                    parts = str(row.get('gcam', '0,0,0')).split(',')
                    tone, anx = float(parts[0]), float(parts[2])
                except: tone, anx = 0.0, 0.0

                cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?)",
                             (gkgid, gkgid[:8], gkgid[:4], row.get('publisher'), row.get('url'), t, row.get('gcam'), tone, anx, assigned_pillar))
                added += 1
    conn.commit()
    return added

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Nepal-Tibet Media Monitor", layout="wide", page_icon="🇳🇵")
conn = init_db()

st.title("🇳🇵 Nepal Media Influence Analyzer (2015-2025)")

with st.sidebar:
    st.header("1. Data Synchronizer")
    files = st.file_uploader("Upload GDELT Archives (CSV/Excel)", accept_multiple_files=True)
    if st.button("Sync & Categorize"):
        if files:
            new = process_and_categorize(conn, files)
            st.success(f"Added {new} high-density articles.")
    
    st.divider()
    st.header("2. Search Explorer")
    user_query = st.text_input("Deep Search (comma-separated)", "Tibet, Xizang")

# --- 4. CORE ANALYSIS ---
df_all = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_all.empty:
    keywords = [k.strip().lower() for k in user_query.split(",") if k.strip()]
    df_viz = df_all[df_all.apply(lambda r: any(kw in (str(r['url'])+str(r['themes'])).lower() for kw in keywords), axis=1)] if keywords else df_all

    # KPI Row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Corpus Size", len(df_viz))
    c2.metric("Avg Tone", round(df_viz['tone'].mean(), 2))
    c3.metric("Avg Anxiety", round(df_viz['anxiety'].mean(), 2))
    c4.metric("Active Years", df_viz['year'].nunique())

    # 1. PILLAR DISTRIBUTION (The Image Requirement)
    st.header("📊 Narrative Pillar Distribution")
    pillar_counts = df_viz['pillar'].value_counts().reset_index()
    st.plotly_chart(px.bar(pillar_counts, x='pillar', y='count', color='pillar', title="Volume by Research Category"))

    # 2. LONGITUDINAL TRAJECTORY
    st.header("📉 Narrative Trajectory (2015-2025)")
    trend = df_viz.groupby(['year', 'pillar']).size().reset_index(name='Articles')
    st.plotly_chart(px.line(trend, x='year', y='Articles', color='pillar', markers=True))

    # 3. SOURCE EXPLORER & DOWNLOAD
    st.header("🔍 Research Source Archive")
    csv = df_viz.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Filtered Corpus (CSV)", csv, "nepal_media_research.csv", "text/csv")
    st.dataframe(df_viz[['year', 'publisher', 'pillar', 'url', 'tone']], use_container_width=True, column_config={"url": st.column_config.LinkColumn()})

    # 4. AI RESEARCH BREAKDOWN
    st.divider()
    if st.button("📝 Generate Detailed Qualitative Analysis"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            context = df_viz.groupby('pillar')['tone'].mean().to_string()
            prompt = f"""
            Analyze these Nepali media findings for a geostrategy report:
            {context}
            Focus on terminology shifts (Tibet vs Xizang), self-censorship, and governance impacts on border infrastructure narratives.
            """
            with st.spinner("Analyzing..."):
                st.markdown(model.generate_content(prompt).text)
        except Exception as e: st.error(f"API Error: {e}")
else:
    st.info("Vault empty. Upload GDELT files to begin.")
