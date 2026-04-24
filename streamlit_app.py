import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import io

# --- 1. RESEARCH DEFINITIONS ---
METHODOLOGY = {
    "Search Mode": "Type any keywords (comma-separated) to filter the entire dataset. Charts will update instantly.",
    "Tone Score": "Overall sentiment (Positive minus Negative).",
    "Anxiety Score": "Negative friction or perceived threat in reporting.",
    "Self-Censorship": "Flagged when state media covers BRI/infrastructure but omits sensitive human rights terminology."
}

# --- 2. DATABASE PERSISTENCE ---
def init_db():
    conn = sqlite3.connect("nepal_influence.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_vault (
            gkgid TEXT PRIMARY KEY, date TEXT, publisher TEXT, url TEXT, 
            themes TEXT, gcam TEXT, tone REAL, anxiety REAL
        )
    """)
    conn.commit()
    return conn

def process_bulk_files(conn, uploaded_files):
    cursor = conn.cursor()
    added = 0
    # Map GDELT columns to internal names
    col_map = {'GKGRECORDID': 'gkgid', 'Publisher': 'publisher', 'SourceCommonName': 'publisher',
               'URL': 'url', 'DocumentIdentifier': 'url', 'Themes': 'themes', 'V2Themes': 'themes', 'GCAM': 'gcam'}

    for file in uploaded_files:
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df = df.rename(columns=col_map)
        
        for _, row in df.iterrows():
            gkgid = str(row.get('gkgid', ''))
            if not gkgid: continue
            
            cursor.execute("SELECT 1 FROM media_vault WHERE gkgid=?", (gkgid,))
            if not cursor.fetchone():
                try:
                    parts = str(row.get('gcam')).split(',')
                    t, a = float(parts[0]), float(parts[2])
                except:
                    t, a = 0.0, 0.0

                cursor.execute("INSERT INTO media_vault VALUES (?,?,?,?,?,?,?,?)",
                             (gkgid, gkgid[:8], row.get('publisher'), row.get('url'), 
                              row.get('themes'), row.get('gcam'), t, a))
                added += 1
    conn.commit()
    return added

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Nepal Media Search Engine", layout="wide")
conn = init_db()

st.title("🇳🇵 Nepal Media Influence Search Engine")

with st.sidebar:
    st.header("1. Data Upload")
    bulk_files = st.file_uploader("Upload CSV/Excel Files", accept_multiple_files=True)
    if st.button("Sync Data"):
        if bulk_files:
            new = process_bulk_files(conn, bulk_files)
            st.success(f"Added {new} new records.")
        else:
            st.warning("No files selected.")
    
    st.divider()
    st.header("2. Global Keyword Filter")
    search_input = st.text_input("Enter Keywords (e.g. Tibet, Xizang, BRI)", "Tibet")
    st.caption("Separate multiple keywords with commas.")

# --- 4. THE SEARCH LOGIC ---
# This pulls everything from the DB and filters based on your input
df_full = pd.read_sql("SELECT * FROM media_vault", conn)

if not df_full.empty:
    keywords = [k.strip().lower() for k in search_input.split(",") if k.strip()]
    
    if keywords:
        # Check if any keyword exists in URL or Themes
        pattern = '|'.join(keywords)
        df_filtered = df_full[
            df_full['url'].str.contains(pattern, case=False, na=False) | 
            df_full['themes'].str.contains(pattern, case=False, na=False)
        ].copy()
    else:
        df_filtered = df_full.copy()

    # --- 5. DYNAMIC VISUALS ---
    st.subheader(f"Analysis for: '{search_input}'")
    
    if not df_filtered.empty:
        df_filtered['Year'] = df_filtered['date'].str[:4]
        
        # KPI Metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Articles Found", len(df_filtered))
        c2.metric("Avg Tone", round(df_filtered['tone'].mean(), 2))
        c3.metric("Avg Anxiety", round(df_filtered['anxiety'].mean(), 2))

        # 1. Trajectory for the specific search
        trend = df_filtered.groupby('Year').size().reset_index(name='Volume')
        st.plotly_chart(px.line(trend, x='Year', y='Volume', markers=True, 
                               title=f"Reporting Volume for '{search_input}' (2015-2025)"))

        # 2. Sentiment Scatter
        st.plotly_chart(px.scatter(df_filtered, x="tone", y="anxiety", color="publisher", 
                                  hover_data=['url'], title="Sentiment Mapping for Search Keywords"))

        # 3. AI Policy Brief for the filtered data
        if st.button("✨ Generate AI Brief for this Search"):
            try:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                model = genai.GenerativeModel('gemini-2.5-flash-lite')
                context = df_filtered[['publisher', 'tone', 'url']].head(15).to_string()
                response = model.generate_content(f"Analyze the media framing for keywords '{search_input}' based on this data: {context}")
                st.markdown(response.text)
            except Exception as e:
                st.error(f"AI Error: {e}")
    else:
        st.warning(f"No data found matching keywords: {search_input}")
else:
    st.info("The database is currently empty. Please upload files in the sidebar.")
