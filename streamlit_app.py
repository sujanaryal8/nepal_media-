import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import requests
import io
import time

# --- 1. RESEARCH DEFINITIONS ---
METHODOLOGY = {
    "Relevant": "Baseline corpus of articles discussing Tibet, Buddhism, or the Dalai Lama.",
    "Amplify": "Narratives aligning with PRC state positions on development, infrastructure, and social harmony.",
    "Normalize": "Framing that encourages the adoption of PRC terminology (e.g., Xizang) and strategic necessity.",
    "Resist": "Content highlighting human rights, border friction, or religious suppression.",
    "Tone Score": "Net emotional charge: Positive minus Negative sentiment (Extracted from GDELT GCAM).",
    "Anxiety Score": "Level of friction or perceived threat (Extracted from GDELT Negative Sentiment scores)."
}

# --- 2. DATABASE & PERSISTENCE ---
def init_db():
    conn = sqlite3.connect("nepal_influence.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_vault (
            gkgid TEXT PRIMARY KEY, date TEXT, publisher TEXT, url TEXT, 
            themes TEXT, gcam TEXT, tone REAL, anxiety REAL, 
            amp INT, norm INT, res INT, rel INT
        )
    """)
    conn.commit()
    return conn

def process_and_save(conn, df, kws):
    cursor = conn.cursor()
    new_entries = 0
    
    # Map GDELT columns to internal names
    col_map = {
        'GKGRECORDID': 'gkgid',
        'SourceCommonName': 'publisher',
        'Publisher': 'publisher',
        'DocumentIdentifier': 'url',
        'URL': 'url',
        'V2Themes': 'themes',
        'Themes': 'themes',
        'GCAM': 'gcam'
    }
    df = df.rename(columns=col_map)

    for _, row in df.iterrows():
        gkgid = str(row.get('gkgid'))
        # Check if exists to avoid double-processing
        cursor.execute("SELECT 1 FROM media_vault WHERE gkgid=?", (gkgid,))
        if not cursor.fetchone():
            text = (str(row.get('url')) + " " + str(row.get('themes'))).lower()
            
            # Pillar Analysis
            is_rel = 1 if any(k in text for k in kws['rel'] if k.strip()) else 0
            is_amp = 1 if is_rel and any(k in text for k in kws['amp'] if k.strip()) else 0
            is_norm = 1 if is_rel and any(k in text for k in kws['norm'] if k.strip()) else 0
            is_res = 1 if is_rel and any(k in text for k in kws['res'] if k.strip()) else 0
            
            # Sentiment Extraction
            try:
                gcam_parts = str(row.get('gcam')).split(',')
                tone, anxiety = float(gcam_parts[0]), float(gcam_parts[2])
            except:
                tone, anxiety = 0.0, 0.0

            cursor.execute("INSERT INTO media_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (gkgid, gkgid[:8], row.get('publisher'), row.get('url'), 
                          row.get('themes'), row.get('gcam'), tone, anxiety, 
                          is_amp, is_norm, is_res, is_rel))
            new_entries += 1
    conn.commit()
    return new_entries

# --- 3. DASHBOARD UI ---
st.set_page_config(page_title="Nepal Media Monitor", layout="wide", page_icon="🇳🇵")
conn = init_db()

st.title("🇳🇵 Nepal Media Influence Monitor (2015-2025)")
st.markdown("### Longitudinal NLP Analysis of PRC-Aligned Narratives")

with st.sidebar:
    st.header("1. Methodology Definitions")
    for term, definition in METHODOLOGY.items():
        st.caption(f"**{term}**: {definition}")
    
    st.divider()
    st.header("2. Manual Keyword Search")
    kw_rel = st.text_area("Relevant (Baseline)", "tibet, buddhism, dalai lama, lhasa").split(",")
    kw_amp = st.text_area("Amplify", "development, harmony, one-china, infrastructure, bri").split(",")
    kw_norm = st.text_area("Normalize", "xizang, partnership, strategic, neighbor").split(",")
    kw_res = st.text_area("Resist", "rights, arrest, border, dispute, suppression").split(",")
    
    st.divider()
    st.header("3. Data Sourcing")
    uploaded_file = st.file_uploader("Upload Enriched GDELT CSV", type=['csv'])

# --- 4. DATA PROCESSING ---
if uploaded_file:
    raw_df = pd.read_csv(uploaded_file)
    kws = {'rel': kw_rel, 'amp': kw_amp, 'norm': kw_norm, 'res': kw_res}
    new_added = process_and_save(conn, raw_df, kws)
    if new_added > 0:
        st.sidebar.success(f"Added {new_added} new articles to vault.")
    else:
        st.sidebar.info("Database is already up to date.")

# Load data from Vault for visualization
df_viz = pd.read_sql("SELECT * FROM media_vault WHERE rel = 1", conn)

if not df_viz.empty:
    df_viz['Year'] = df_viz['date'].str[:4]
    
    # Metrics Row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Corpus", len(df_viz))
    m2.metric("Amplify", df_viz['amp'].sum())
    m3.metric("Normalize", df_viz['norm'].sum())
    m4.metric("Resist", df_viz['res'].sum())

    # Visual 1: Trajectory
    st.subheader("Narrative Trajectory (2015-2025)")
    trend = df_viz.groupby('Year')[['amp', 'norm', 'res']].sum().reset_index()
    fig_line = px.line(trend, x='Year', y=['amp', 'norm', 'res'], markers=True,
                      title="Pillar Evolution in Nepal's Information Space",
                      color_discrete_map={"amp": "#EF553B", "norm": "#636EFA", "res": "#00CC96"})
    st.plotly_chart(fig_line, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Sentiment: Tone vs. Anxiety")
        fig_scatter = px.scatter(df_viz, x="tone", y="anxiety", color="publisher",
                                hover_data=['url'], title="Editorial Framing Scatter")
        st.plotly_chart(fig_scatter, use_container_width=True)
    
    with col_b:
        st.subheader("Terminology Shift: Tibet vs. Xizang")
        df_viz['Term'] = df_viz['url'].apply(lambda x: 'Xizang' if 'xizang' in str(x).lower() else 'Tibet')
        term_df = df_viz.groupby(['Year', 'Term']).size().reset_index(name='Count')
        fig_term = px.bar(term_df, x='Year', y='Count', color='Term', barmode='group')
        st.plotly_chart(fig_term, use_container_width=True)

    # --- 5. AI POLICY BRIEF ---
    st.divider()
    st.header("✨ AI-Powered Policy Brief")
    if st.button("Generate Trend Analysis"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            # Using Lite model for higher 15 RPM quota
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            
            sample_data = df_viz[['publisher', 'tone', 'amp']].head(15).to_string()
            prompt = f"""
            Analyze the following media monitoring data for a policy brief on Nepal-China relations. 
            Focus on narrative alignment, self-censorship, and terminology shifts regarding Tibet.
            Data: {sample_data}
            """
            
            with st.spinner("Gemini is analyzing 10 years of media framing..."):
                response = model.generate_content(prompt)
                st.markdown(response.text)
        except Exception as e:
            if "429" in str(e):
                st.error("Rate limit hit. Please wait 60 seconds. (Free Tier Limit)")
            else:
                st.error(f"Configuration Error: {e}")
else:
    st.info("👋 Welcome! Please upload your analyzed CSV in the sidebar to populate the monitor.")
