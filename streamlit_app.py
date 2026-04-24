import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import io

# --- 1. RESEARCH DEFINITIONS ---
METHODOLOGY = {
    "Self-Censorship": "Flagged when articles discuss China/BRI but omit sensitive rights-based keywords.",
    "Narrative Pillars": "Amplify (Alignment), Normalize (Naming Shifts), Resist (Political Friction).",
    "Keyword Hits": "Frequency count of individual keywords within the filtered corpus."
}

# --- 2. DATABASE PERSISTENCE ---
def init_db():
    conn = sqlite3.connect("nepal_influence.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS research_vault (
            gkgid TEXT PRIMARY KEY, date TEXT, year TEXT, publisher TEXT, url TEXT, 
            themes TEXT, gcam TEXT, tone REAL, anxiety REAL, 
            amplify INT, normalize INT, resist INT, self_censor INT, relevant INT
        )
    """)
    conn.commit()
    return conn

def process_data(conn, files):
    cursor = conn.cursor()
    added = 0
    col_map = {'GKGRECORDID': 'gkgid', 'Publisher': 'publisher', 'SourceCommonName': 'publisher',
               'URL': 'url', 'DocumentIdentifier': 'url', 'Themes': 'themes', 'V2Themes': 'themes', 'GCAM': 'gcam'}
    
    state_media = ['gorkhapatra', 'risingnepal', 'rss', 'nepal news agency']
    sensitive = ['rights', 'refugee', 'dalai', 'cta', 'dispute', 'arrest', 'border']

    for file in files:
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df = df.rename(columns=col_map)
        for _, row in df.iterrows():
            gkgid = str(row.get('gkgid', ''))
            if not gkgid or gkgid == 'nan': continue
            cursor.execute("SELECT 1 FROM research_vault WHERE gkgid=?", (gkgid,))
            if not cursor.fetchone():
                u, t = str(row.get('url', '')).lower(), str(row.get('themes', '')).lower()
                rel = 1 if any(k in (u+t) for k in ['tibet', 'xizang', 'buddhism', 'lama']) else 0
                amp = 1 if rel and any(k in (u+t) for k in ['development', 'harmony', 'infrastructure', 'bri']) else 0
                res = 1 if rel and any(k in (u+t) for k in sensitive) else 0
                
                is_state = any(sm in str(row.get('publisher')).lower() for sm in state_media)
                sc = 1 if (is_state and 'china' in (u+t) and not any(s in (u+t) for s in sensitive)) else 0
                
                try:
                    parts = str(row.get('gcam', '0,0,0')).split(',')
                    tone, anx = float(parts[0]), float(parts[2])
                except: tone, anx = 0.0, 0.0

                cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (gkgid, gkgid[:8], gkgid[:4], row.get('publisher'), row.get('url'), t, row.get('gcam'), tone, anx, amp, 0, res, sc, rel))
                added += 1
    conn.commit()
    return added

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Media Influence Monitor", layout="wide", page_icon="🇳🇵")
conn = init_db()

st.title("🇳🇵 Nepal-China Media Influence & Narrative Analyzer")

with st.sidebar:
    st.header("1. Data Synchronizer")
    files = st.file_uploader("Bulk Upload CSV/Excel", accept_multiple_files=True)
    if st.button("Sync Research Database"):
        if files:
            new = process_data(conn, files)
            st.success(f"Added {new} new articles.")
    
    st.divider()
    st.header("2. Search & Filter")
    user_query = st.text_input("Deep Search (comma-separated)", "Tibet, Xizang, BRI")

# --- 4. CORE ANALYSIS LOGIC ---
df_all = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_all.empty:
    keywords = [k.strip().lower() for k in user_query.split(",") if k.strip()]
    
    if keywords:
        def match_fn(row):
            text = (str(row['url']) + " " + str(row['themes'])).lower()
            return any(kw in text for kw in keywords)
        df_viz = df_all[df_all.apply(match_fn, axis=1)].copy()
    else:
        df_viz = df_all[df_all['relevant'] == 1].copy()

    if not df_viz.empty:
        # KPI Row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Dataset Size", len(df_viz))
        c2.metric("Narrative Alignment", df_viz['amplify'].sum())
        c3.metric("Political Friction", df_viz['resist'].sum())
        c4.metric("Self-Censorship Count", df_viz['self_censor'].sum())

        # 1. KEYWORD FREQUENCY ANALYSIS (NEW REQUIREMENT)
        st.header("📊 Keyword Frequency & Distribution")
        kw_data = []
        for kw in keywords:
            count = df_viz['url'].str.contains(kw, case=False).sum() + df_viz['themes'].str.contains(kw, case=False).sum()
            kw_data.append({"Keyword": kw.upper(), "Frequency": count})
        
        kw_df = pd.DataFrame(kw_data)
        st.plotly_chart(px.bar(kw_df, x="Keyword", y="Frequency", color="Keyword", title="Keyword Performance in Current Search"))

        # 2. LONGITUDINAL TRAJECTORY
        st.header("📉 Narrative Trajectory (2015-2025)")
        trend = df_viz.groupby(['year', 'publisher']).size().reset_index(name='Articles')
        st.plotly_chart(px.line(trend, x='year', y='Articles', color='publisher', markers=True, title="Reporting Frequency per Media House"))

        # 3. SENTIMENT & ANXIETY ANALYSIS
        st.header("🎭 High-Fidelity Sentiment Mapping")
        st.plotly_chart(px.scatter(df_viz, x="tone", y="anxiety", color="publisher", hover_data=['url'], title="Tone vs. Anxiety distribution"))

        # 4. SOURCE EXPLORER
        st.header("🔍 Research Source Archive")
        display_df = df_viz[['year', 'publisher', 'url', 'tone', 'anxiety']].copy()
        display_df.columns = ['Year', 'Media House', 'URL', 'Tone', 'Anxiety']
        st.dataframe(display_df, use_container_width=True, column_config={"URL": st.column_config.LinkColumn()})

        # --- 5. DETAILED ANALYSIS GENERATOR ---
        st.divider()
        st.header("📝 Detailed Research Breakdown")
        if st.button("Generate Detailed Analysis & Insights"):
            try:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-flash-lite')
                
                # Context injection: Stats and Keyword counts
                context = f"Query: {user_query}. Stats: {kw_df.to_string(index=False)}. Self-Censor: {df_viz['self_censor'].sum()}"
                
                prompt = f"""
                Act as a Senior Media Researcher. Based on these quantitative findings:
                {context}
                
                Write a detailed qualitative analysis report including:
                1. Impact of Terminology Shifts (Xizang vs Tibet).
                2. Patterns of Self-Censorship in state-owned vs private media.
                3. Trajectory of Chinese narrative alignment from 2015 to 2025.
                4. Strategic implications for the Nepali information space.
                """
                
                with st.spinner("Analyzing data patterns..."):
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
            except Exception as e: st.error(f"API Error: {e}")
    else:
        st.warning(f"No results for: {user_query}")
else:
    st.info("Database is empty. Please upload files in the sidebar.")
