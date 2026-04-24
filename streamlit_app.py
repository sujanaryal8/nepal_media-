import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import io

# --- 1. RESEARCH DEFINITIONS ---
METHODOLOGY = {
    "Pillars": "Amplify (PRC alignment), Normalize (Terminology shifts), Resist (Friction/Human Rights).",
    "Self-Censorship": "Flagged when State media (Gorkhapatra/Rising Nepal) covers BRI/Infrastructure but omits sensitive human rights/refugee keywords.",
    "CTA & Disputes": "Uses specialized GDELT themes like 'TAX_ETHNICITY_TIBETANS' and 'BORDER_DISPUTE'.",
    "NLP Metrics": "Tone (Positive-Negative balance) and Anxiety (Friction/Threat levels)."
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

def process_and_analyze(conn, uploaded_files):
    cursor = conn.cursor()
    added = 0
    # Mapping for various GDELT and manually curated formats
    col_map = {'GKGRECORDID': 'gkgid', 'Publisher': 'publisher', 'SourceCommonName': 'publisher',
               'URL': 'url', 'DocumentIdentifier': 'url', 'Themes': 'themes', 'V2Themes': 'themes', 'GCAM': 'gcam'}

    state_media = ['gorkhapatra', 'risingnepal', 'nepal news agency', 'rss']
    sensitive_kws = ['rights', 'human rights', 'refugee', 'dalai', 'cta', 'dispute', 'arrest', 'border']

    for file in uploaded_files:
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df = df.rename(columns=col_map)
        
        for _, row in df.iterrows():
            gkgid = str(row.get('gkgid', ''))
            if not gkgid: continue
            
            cursor.execute("SELECT 1 FROM research_vault WHERE gkgid=?", (gkgid,))
            if not cursor.fetchone():
                url = str(row.get('url', '')).lower()
                themes = str(row.get('themes', '')).lower()
                pub = str(row.get('publisher', '')).lower()
                
                # 1. Relevance Check (Baseline Corpus)
                relevant = 1 if any(k in (url + themes) for k in ['tibet', 'xizang', 'buddhism', 'buddhist', 'lama']) else 0
                
                # 2. Research Pillars Analysis
                amp = 1 if relevant and any(k in (url + themes) for k in ['development', 'harmony', 'infrastructure', 'one-china', 'bri']) else 0
                norm = 1 if relevant and 'xizang' in (url + themes) else 0
                res = 1 if relevant and any(k in (url + themes) for k in sensitive_kws) else 0
                
                # 3. Self-Censorship Detection Logic
                # Flagged if state media mentions BRI/China but avoids all sensitive Tibetan/Rights keywords
                is_state = any(sm in pub for sm in state_media)
                mentions_china = any(c in (url + themes) for c in ['china', 'bri', 'belt and road'])
                has_sensitive = any(s in (url + themes) for s in sensitive_kws)
                self_censor = 1 if (is_state and mentions_china and not has_sensitive) else 0

                try:
                    parts = str(row.get('gcam')).split(',')
                    t, a = float(parts[0]), float(parts[2])
                except:
                    t, a = 0.0, 0.0

                cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (gkgid, gkgid[:8], gkgid[:4], row.get('publisher'), row.get('url'), 
                              row.get('themes'), row.get('gcam'), t, a, amp, norm, res, self_censor, relevant))
                added += 1
    conn.commit()
    return added

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Nepal Tibet Media Monitor", layout="wide")
conn = init_db()

st.title("🇳🇵 Nepal Media Influence & Narrative Monitor")

with st.sidebar:
    st.header("1. Bulk Data Sync")
    bulk_files = st.file_uploader("Upload Articles (CSV/Excel)", accept_multiple_files=True)
    if st.button("Synchronize Research Vault"):
        if bulk_files:
            new = process_and_analyze(conn, bulk_files)
            st.success(f"Added {new} new records to longitudinal database.")
        else:
            st.warning("Please upload files first.")
    
    st.divider()
    st.header("2. Manual Exploration")
    user_search = st.text_input("Deep Search (e.g. 'Human Rights', 'Border')", "")

# --- 4. DATA PROCESSING & VISUALIZATION ---
df_all = pd.read_sql("SELECT * FROM research_vault", conn)

if not df_all.empty:
    # Apply user filter if provided, otherwise show relevant corpus
    if user_search:
        df_viz = df_all[df_all['url'].str.contains(user_search, case=False) | df_all['themes'].str.contains(user_search, case=False)].copy()
    else:
        df_viz = df_all[df_all['relevant'] == 1].copy()

    # Metric Dashboard
    st.subheader("High-Fidelity Research Metrics")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Articles", len(df_viz))
    c2.metric("Amplify", df_viz['amplify'].sum())
    c3.metric("Resist (Friction)", df_viz['resist'].sum())
    c4.metric("Self-Censorship", df_viz['self_censor'].sum())
    c5.metric("Avg Tone", round(df_viz['tone'].mean(), 2))

    # Visual 1: Longitudinal Trajectory (The Requirement)
    st.subheader("Narrative Trajectory (2015-2025)")
    trend = df_viz.groupby(['year', 'publisher']).size().reset_index(name='Count')
    st.plotly_chart(px.line(trend, x='year', y='Count', color='publisher', markers=True, title="Reporting Frequency per Publisher"))

    # Visual 2: Editorial Framing (Tone vs Anxiety)
    st.subheader("Editorial Framing Analysis")
    st.plotly_chart(px.scatter(df_viz, x="tone", y="anxiety", color="publisher", size_max=10, 
                              hover_data=['url'], title="Sentiment Mapping: PRC Alignment vs. Critical Friction"))

    # Visual 3: Terminology Transformation
    st.subheader("Terminology Shift: Tibet vs. Xizang")
    df_viz['Term'] = df_viz['url'].apply(lambda x: 'Xizang' if 'xizang' in str(x).lower() else 'Tibet')
    term_shift = df_viz.groupby(['year', 'Term']).size().reset_index(name='Count')
    st.plotly_chart(px.bar(term_shift, x='year', y='Count', color='Term', barmode='group', title="Shift toward PRC-standard Terminology"))

    # --- 5. AI GENERATOR ---
    st.divider()
    if st.button("✨ Generate Comprehensive Policy Brief"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            # Feeding quantitative results to the AI
            stats = f"Amplify: {df_viz['amplify'].sum()}, Resist: {df_viz['resist'].sum()}, Self-Censor: {df_viz['self_censor'].sum()}"
            response = model.generate_content(f"Write a policy brief on Nepal-China media framing based on these results: {stats}. Focus on self-censorship and Tibet.")
            st.markdown(response.text)
        except Exception as e:
            st.error(f"API Error: {e}")
else:
    st.info("Database empty. Upload files to generate longitudinal analysis.")
