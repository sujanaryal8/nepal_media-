import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import io

# --- 1. TNNM SYSTEM CONFIGURATION ---
ST_COLOR_MAP = {
    "Propaganda / Manufactured Spin": "#FF9800",   # Orange
    "Severe Suppression / Active Censorship": "#F44336", # Red
    "Routine Statecraft / Bureaucratic Tone": "#9E9E9E", # Grey
    "Baseline Regional Tone": "#4CAF50"            # Green
}

# --- 2. CORE UTILITIES ---
def load_tnnm_data(file):
    try:
        df = pd.read_csv(file)
        # Ensure DATE is datetime for longitudinal plotting
        df['DATE'] = pd.to_datetime(df['DATE'])
        df['YEAR'] = df['DATE'].dt.year
        return df
    except Exception as e:
        st.error(f"Schema Error: Ensure file matches TNNM v1.0 Schema. {e}")
        return None

# --- 3. UI LAYOUT & SIDEBAR ---
st.set_page_config(page_title="TNNM Geopolitical Monitor", layout="wide")

st.title("🇳🇵 TNNM Geopolitical Corpus Analyzer")
st.caption("Version 1.0 | ETL & NLP/GCAM Scoring Pipeline")

with st.sidebar:
    st.header("I. Data Operations")
    uploaded_file = st.file_uploader("Upload TNNM_Geopolitical_Corpus_Final.csv", type=['csv'])
    
    st.divider()
    st.header("II. Filters (Level 2 Analyst)")
    if uploaded_file:
        # Load data once
        df = load_tnnm_data(uploaded_file)
        if df is not None:
            selected_keywords = st.multiselect(
                "Filter by Dashboard Keywords", 
                options=df['Dashboard_Keywords'].dropna().unique(),
                default=None
            )
            selected_flags = st.multiselect(
                "Editorial Flag Filter", 
                options=df['Editorial_Flag'].unique(),
                default=df['Editorial_Flag'].unique()
            )

# --- 4. DASHBOARD LOGIC ---
if uploaded_file and df is not None:
    # Filtering Logic
    filtered_df = df[df['Editorial_Flag'].isin(selected_flags)]
    if selected_keywords:
        filtered_df = filtered_df[filtered_df['Dashboard_Keywords'].isin(selected_keywords)]

    # --- TIER 1: EXECUTIVE VIEW ---
    st.header("📊 Executive Summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Corpus Size", len(filtered_df))
    m2.metric("Suppression Cases", len(filtered_df[filtered_df['Editorial_Flag'] == "Severe Suppression / Active Censorship"]))
    m3.metric("Avg Censorship Delta", round(filtered_df['Censorship_Delta'].mean(), 2))
    m4.metric("Avg Literal Score", round(filtered_df['Literal_Text_Score'].mean(), 2))

    # Narrative Trajectory by Editorial Flag
    st.subheader("Longitudinal Narrative Trajectory (2015-2025)")
    trend_df = filtered_df.groupby(['YEAR', 'Editorial_Flag']).size().reset_index(name='Count')
    fig_trend = px.line(trend_df, x='YEAR', y='Count', color='Editorial_Flag', 
                        color_discrete_map=ST_COLOR_MAP, markers=True,
                        title="Evolution of Media Spin vs. Suppression")
    st.plotly_chart(fig_trend, use_container_width=True)

    # --- TIER 2: ANALYST VIEW ---
    st.divider()
    st.header("🕵️ Analyst Deep-Dive")
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("Censorship Delta by Publisher")
        pub_delta = filtered_df.groupby('SourceCommonName')['Censorship_Delta'].mean().sort_values().reset_index()
        fig_delta = px.bar(pub_delta, x='Censorship_Delta', y='SourceCommonName', orientation='h',
                          title="Media Muting vs. Amplification Index",
                          color='Censorship_Delta', color_continuous_scale='RdYlGn_r')
        st.plotly_chart(fig_delta, use_container_width=True)

    with col_b:
        st.subheader("Text Intensity vs. Subtext Gravity")
        fig_scatter = px.scatter(filtered_df, x="Literal_Text_Score", y="Subtext_Gravity_Score",
                                color="Editorial_Flag", color_discrete_map=ST_COLOR_MAP,
                                hover_data=['SourceCommonName', 'Dashboard_Keywords'],
                                title="Forensic Mapping of Geopolitical Threat")
        st.plotly_chart(fig_scatter, use_container_width=True)

    # --- TIER 3: FORENSIC VIEW ---
    st.divider()
    st.header("🧬 Forensic Psycholinguistic Engine")
    
    # Radar Chart / Multi-axis for Psycholinguistic Proof
    st.subheader("Scaled Linguistic Indicators (Composite)")
    forensic_metrics = ["S_Anger", "S_Anxiety", "S_Complexity", "S_Tentative", "S_ActRef"]
    avg_metrics = filtered_df[forensic_metrics].mean().reset_index()
    avg_metrics.columns = ['Metric', 'Score']
    
    fig_forensic = px.line_polar(avg_metrics, r='Score', theta='Metric', line_close=True,
                                title="Composite Psycholinguistic Proof of Narrative Direction")
    st.plotly_chart(fig_forensic, use_container_width=True)

    # Data Table (Level 3 Detail)
    st.subheader("Forensic Source Archive")
    st.dataframe(filtered_df[['DATE', 'SourceCommonName', 'Editorial_Flag', 'Censorship_Delta', 'DocumentIdentifier']], 
                 use_container_width=True, 
                 column_config={"DocumentIdentifier": st.column_config.LinkColumn("Source URL")})

    # AI Research Detail (TNNM Research Report)
    if st.button("📝 Generate TNNM Research Breakdown"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            
            # Send stats for analysis
            stats_context = f"""
            TNNM Analysis Context:
            Keywords: {selected_keywords}
            Editorial Flags: {filtered_df['Editorial_Flag'].value_counts().to_dict()}
            Avg Censorship Delta: {filtered_df['Censorship_Delta'].mean()}
            Forensic Averages: {filtered_df[forensic_metrics].mean().to_dict()}
            """
            
            prompt = f"""
            Act as a Senior Geopolitical Intelligence Analyst. Analyze the following TNNM media data:
            {stats_context}
            
            Please provide a detailed report including:
            1. Evidence of 'Manufactured Spin' vs 'Active Censorship'.
            2. The relationship between S_Anxiety and Censorship_Delta.
            3. Trajectory of Sino-Nepali media alignment based on Subtext Gravity.
            4. Strategic implications for the information space regarding Tibetan sovereignty.
            """
            
            with st.spinner("AI Analyst is processing Forensic Metrics..."):
                response = model.generate_content(prompt)
                st.markdown(response.text)
        except Exception as e:
            st.error(f"Intelligence Engine Error: {e}")

else:
    st.info("Awaiting TNNM_Geopolitical_Corpus_Final.csv upload to initialize monitor.")
