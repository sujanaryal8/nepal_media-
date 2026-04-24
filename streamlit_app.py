import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import io

# --- 1. RESEARCH DEFINITIONS ---
METHODOLOGY = {
    "Pillars": "Amplify (PRC alignment), Normalize (Terminology shifts), Resist (Friction/Human Rights).",
    "Source Explorer": "A searchable database of all articles matching your keyword criteria.",
    "Self-Censorship": "Flagged when state media covers BRI but omits sensitive rights keywords."
}

# --- 2. DATABASE LOGIC ---
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

def process_bulk(conn, files):
    cursor = conn.cursor()
    added = 0
    col_map = {'GKGRECORDID': 'gkgid', 'Publisher': 'publisher', 'SourceCommonName': 'publisher',
               'URL': 'url', 'DocumentIdentifier': 'url', 'Themes': 'themes', 'V2Themes': 'themes', 'GCAM': 'gcam'}
    
    state_media = ['gorkhapatra', 'risingnepal', 'nepal news agency', 'rss']
    sensitive_kws = ['rights', 'human rights', 'refugee', 'dalai', 'cta', 'dispute', 'arrest', 'border']

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
                res = 1 if rel and any(k in (u+t) for k in sensitive_kws) else 0
                sc = 1 if (any(sm in str(row.get('publisher')).lower() for sm in state_media) and 'china' in (u+t) and not any(s in (u+t) for s in sensitive_kws)) else 0
                
                try:
                    parts = str(row.get('gcam')).split(',')
                    tone, anx = float(parts[0]), float(parts[2])
                except: tone, anx = 0.0, 0.0

                cursor.execute("INSERT INTO research_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (gkgid, gkgid[:8], gkgid[:4], row.get('publisher'), row.get('url'), t, row.get('gcam'), tone, anx, amp, 0, res, sc, rel))
                added += 1
    conn.commit()
    return added

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Nepal Tibet Media Monitor", layout="wide")
conn = init_db()

st.title("🇳🇵 Nepal Media Influence & Source Explorer")

with st.sidebar:
    st.header("1. Data Sourcing")
    files = st.file_uploader("Upload Articles (CSV/Excel)", accept_multiple_files=True)
    if st.button("Sync Database"):
        if files:
            new = process_bulk(conn, files)
            st.success(f"Added {new} new articles.")
    
    st.divider()
    st.header("2. Search & Filter")
    user_query = st.text_input("Filter by Keyword (e.g. 'Border', 'CTA')", "")

# --- 4. DATA VIZ ---
df_all = pd.read_sql("SELECT * FROM research_vault", conn)
if not df_all.empty:
    df_viz = df_all[df_all['url'].str.contains(user_query, case=False) | df_all['themes'].str.contains(user_query, case=False)] if user_query else df_all[df_all['relevant'] == 1]
    
    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sources Found", len(df_viz))
    c2.metric("Amplify Pillar", df_viz['amplify'].sum())
    c3.metric("Resist Pillar", df_viz['resist'].sum())
    c4.metric("Self-Censorship", df_viz['self_censor'].sum())

    # Trajectory & Sentiment
    st.plotly_chart(px.line(df_viz.groupby('year').size().reset_index(name='Count'), x='year', y='Count', markers=True, title="Reporting Frequency over Time"))
    
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Top Publishers for these Keywords")
        pub_counts = df_viz['publisher'].value_counts().reset_index()
        st.plotly_chart(px.bar(pub_counts, x='publisher', y='count', color='publisher', title="Active Media Houses"))
    with col_r:
        st.subheader("Sentiment Distribution")
        st.plotly_chart(px.scatter(df_viz, x="tone", y="anxiety", color="publisher", hover_data=['url']))

    # --- 5. SOURCE EXPLORER (The New Requirement) ---
    st.divider()
    st.header("🔍 Source Explorer: Matching Articles")
    st.markdown(f"The following sources reference the keywords: **'{user_query}'**")
    
    # Clean the dataframe for display
    display_df = df_viz[['year', 'publisher', 'url', 'tone', 'anxiety']].copy()
    display_df = display_df.rename(columns={'year': 'Year', 'publisher': 'Media House', 'url': 'Source URL', 'tone': 'Tone Score'})
    
    # Interactive Table
    st.dataframe(display_df, use_container_width=True, column_config={
        "Source URL": st.column_config.LinkColumn("Source URL")
    })

    # AI BRIEF
    if st.button("✨ Generate AI Policy Brief from these Sources"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            stats = f"Context: {user_query}. Sources: {len(df_viz)}. Tone: {df_viz['tone'].mean()}"
            response = model.generate_content(f"Analyze the framing of these {len(df_viz)} sources regarding {user_query}: {stats}")
            st.markdown(response.text)
        except Exception as e: st.error(f"API Error: {e}")
else:
    st.info("Vault is empty. Upload files to begin.")
