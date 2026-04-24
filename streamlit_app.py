import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import requests
import io
import re

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("nepal_media.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_data (
            GKGRECORDID TEXT PRIMARY KEY,
            DATE TEXT,
            PUBLISHER TEXT,
            URL TEXT,
            GCAM TEXT,
            THEMES TEXT
        )
    """)
    conn.commit()
    return conn

def insert_data(conn, data):
    cursor = conn.cursor()
    # Normalize column names for GDELT format
    col_map = {
        'GKGRECORDID': 'GKGRECORDID',
        'DATE': 'DATE',
        'Publisher': 'PUBLISHER',
        'SourceCommonName': 'PUBLISHER',
        'DocumentIdentifier': 'URL',
        'URL': 'URL',
        'GCAM': 'GCAM',
        'V2Themes': 'THEMES',
        'Themes': 'THEMES'
    }
    data = data.rename(columns=col_map)
    
    for _, row in data.iterrows():
        cursor.execute("""
            INSERT OR IGNORE INTO media_data (GKGRECORDID, DATE, PUBLISHER, URL, GCAM, THEMES)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (str(row.get('GKGRECORDID')), str(row.get('DATE')), str(row.get('PUBLISHER')), 
              str(row.get('URL')), str(row.get('GCAM')), str(row.get('THEMES'))))
    conn.commit()

# --- ANALYSIS HELPERS ---
def extract_metrics(gcam):
    try:
        parts = str(gcam).split(',')
        return float(parts[0]), float(parts[2]) # Tone, Anxiety
    except:
        return 0.0, 0.0

def count_keywords(text, keywords):
    text = str(text).lower()
    return sum(text.count(kw.strip().lower()) for kw in keywords if kw.strip())

# --- STREAMLIT UI ---
st.set_page_config(page_title="Nepal Media Monitor", layout="wide")
conn = init_db()

st.title("🇳🇵 Nepal Media Influence Dashboard (2015-2025)")

# Sidebar Configuration
st.sidebar.header("1. Data Management")
uploaded_file = st.sidebar.file_uploader("Upload GDELT CSV", type=["csv"])

if uploaded_file:
    df_upload = pd.read_csv(uploaded_file)
    insert_data(conn, df_upload)
    st.sidebar.success("Data Synchronized with Local Database.")

st.sidebar.header("2. Research Pillars")
amp_kws = st.sidebar.text_area("Amplify", "development, harmony, one-china").split(',')
norm_kws = st.sidebar.text_area("Normalize", "xizang, partnership, strategic").split(',')
res_kws = st.sidebar.text_area("Resist", "rights, arrest, border, dispute").split(',')
rel_kws = st.sidebar.text_area("Relevant (Baseline)", "tibet, buddhism, dalai lama").split(',')

# --- LOAD & PROCESS DATA ---
data = pd.read_sql_query("SELECT * FROM media_data", conn)

if not data.empty:
    # Process NLP Metrics
    data[['Tone', 'Anxiety']] = data['GCAM'].apply(lambda x: pd.Series(extract_metrics(x)))
    
    # Analyze Pillars
    data['Content_Full'] = data['URL'].astype(str) + " " + data['THEMES'].astype(str)
    data['Amplify_Score'] = data['Content_Full'].apply(lambda x: count_keywords(x, amp_kws))
    data['Normalize_Score'] = data['Content_Full'].apply(lambda x: count_keywords(x, norm_kws))
    data['Resist_Score'] = data['Content_Full'].apply(lambda x: count_keywords(x, res_kws))
    data['Is_Relevant'] = data['Content_Full'].apply(lambda x: 1 if count_keywords(x, rel_kws) > 0 else 0)

    # Sidebar Hits
    st.sidebar.divider()
    st.sidebar.write(f"**Keyword Hits:**")
    st.sidebar.write(f"Amplify: {data['Amplify_Score'].sum()}")
    st.sidebar.write(f"Resist: {data['Resist_Score'].sum()}")

    # --- VISUALIZATIONS ---
    st.header("Methodology")
    st.info("Analysis covers longitudinal media alignment regarding Tibet and Buddhism using GDELT V2 metadata.")

    # 1. Trajectory
    st.subheader("Narrative Trajectory (2015-2025)")
    data['Year'] = data['DATE'].astype(str).str[:4]
    df_rel = data[data['Is_Relevant'] == 1]
    
    if not df_rel.empty:
        trajectory = df_rel.groupby('Year')[['Amplify_Score', 'Normalize_Score', 'Resist_Score']].sum().reset_index()
        fig_line = px.line(trajectory, x='Year', y=['Amplify_Score', 'Normalize_Score', 'Resist_Score'], 
                          markers=True, title="Pillar Frequency over Time")
        st.plotly_chart(fig_line, use_container_width=True)

        # 2. Sentiment
        st.subheader("Sentiment Analysis: Tone vs. Anxiety")
        fig_scatter = px.scatter(df_rel, x='Tone', y='Anxiety', color='PUBLISHER', 
                                hover_data=['URL'], title="Editorial Framing by Media House")
        st.plotly_chart(fig_scatter, use_container_width=True)

        # 3. Terminology
        st.subheader("Terminology Tracker")
        tibet_c = df_rel['Content_Full'].str.count('tibet').sum()
        xizang_c = df_rel['Content_Full'].str.count('xizang').sum()
        fig_bar = px.bar(x=['Tibet', 'Xizang'], y=[tibet_c, xizang_c], labels={'x':'Term', 'y':'Count'})
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- AI POLICY BRIEF ---
    st.divider()
    st.header("AI-Generated Policy Brief")
    if st.button("Generate Brief"):
        try:
            # Use secrets for the API Key
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash')
            context = df_rel[['PUBLISHER', 'Tone']].head(10).to_string()
            response = model.generate_content(f"Write a short policy brief on Nepal-China media alignment based on this data: {context}")
            st.markdown(response.text)
        except Exception as e:
            st.error(f"API Error: Ensure GEMINI_API_KEY is set in Streamlit Secrets. {e}")

else:
    st.warning("Please upload a GDELT CSV file to begin analysis.")
