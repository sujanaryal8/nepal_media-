import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import io

# --- 1. TNNM SYSTEM CONFIGURATION ---
ST_COLOR_MAP = {
    "Propaganda / Manufactured Spin": "#FF9800",   
    "Severe Suppression / Active Censorship": "#F44336", 
    "Routine Statecraft / Bureaucratic Tone": "#9E9E9E", 
    "Baseline Regional Tone": "#4CAF50"            
}

# --- 2. RESEARCH PILLARS & TWO-GATE LOGIC ---
PILLARS = {
    "Geographic Identity": ["Tibet", "Xizang", "TAR", "Roof of the World"],
    "Diplomatic & Legal": ["One-China", "Belt and Road", "BRI", "Gentleman's Agreement", "MLAT", "Extradition"],
    "Dissent & Activism": ["Dalai Lama", "Tibetan refugee", "Free Tibet", "CTA", "separatism"],
    "Border Infrastructure": ["Shigatse", "Gyirong", "Kerung", "securitization", "liveable villages"],
    "Media Influence": ["Confucius Institute", "mask diplomacy", "soft power", "RSS", "Samachar Samiti"]
}

# Exclusions for Gate 2 Noise Reduction
EXCLUSIONS = [
    "spiritual tourism", "monastery tour", "Everest expedition", "Kailash",
    "trade deficit", "import tariff", "weather", "snowfall", "landslide",
    "domestic politics", "parliamentary debate"
]

def apply_semantic_gates(df):
    """Automates the filtering of irrelevant news based on the Two-Gate logic."""
    # Gate 1: Check for Pillar Keywords
    pattern = '|'.join([kw for pillar in PILLARS.values() for kw in pillar])
    df = df[df['Dashboard_Keywords'].str.contains(pattern, case=False, na=False)]
    
    # Gate 2: Apply Exclusions (NOT logic)
    exclude_pattern = '|'.join(EXCLUSIONS)
    df = df[~df['Dashboard_Keywords'].str.contains(exclude_pattern, case=False, na=False)]
    
    # Pillar Assignment
    def assign_pillar(row):
        for pillar, kws in PILLARS.items():
            if any(kw.lower() in str(row['Dashboard_Keywords']).lower() for kw in kws):
                return pillar
        return "Uncategorized"
    
    df['Research_Pillar'] = df.apply(assign_pillar, axis=1)
    return df

# --- 3. CORE UTILITIES ---
def load_tnnm_data(file):
    try:
        df = pd.read_csv(file)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df['YEAR'] = df['DATE'].dt.year
        return apply_semantic_gates(df)
    except Exception as e:
        st.error(f"Schema Error: {e}")
        return None

# --- 4. UI LAYOUT & SIDEBAR ---
st.set_page_config(page_title="TNNM Geopolitical Monitor", layout="wide")

st.title("🇳🇵 TNNM Geopolitical Corpus Analyzer")
st.caption("Phase 2: Automated Semantic Gating & Pillar Analysis")

with st.sidebar:
    st.header("I. Data Operations")
    uploaded_file = st.file_uploader("Upload TNNM_Geopolitical_Corpus_Final.csv", type=['csv'])
    
    if uploaded_file:
        df = load_tnnm_data(uploaded_file)
        if df is not None:
            st.divider()
            st.header("II. Pillar Filtering")
            selected_pillars = st.multiselect("Research Pillars", options=list(PILLARS.keys()), default=list(PILLARS.keys()))
            selected_flags = st.multiselect("Editorial Flags", options=df['Editorial_Flag'].unique(), default=df['Editorial_Flag'].unique())

# --- 5. DASHBOARD LOGIC ---
if uploaded_file and df is not None:
    filtered_df = df[(df['Editorial_Flag'].isin(selected_flags)) & (df['Research_Pillar'].isin(selected_pillars))]

    # --- TIER 1: EXECUTIVE VIEW ---
    st.header("📊 Pillar Distribution")
    p1, p2 = st.columns([1, 2])
    with p1:
        pillar_counts = filtered_df['Research_Pillar'].value_counts()
        st.plotly_chart(px.pie(names=pillar_counts.index, values=pillar_counts.values, hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel), use_container_width=True)
    with p2:
        st.metric("Clean Corpus Size", len(filtered_df), help="Post-Gate 2 Noise Reduction")
        trend_df = filtered_df.groupby(['YEAR', 'Research_Pillar']).size().reset_index(name='Count')
        st.plotly_chart(px.area(trend_df, x='YEAR', y='Count', color='Research_Pillar', title="Pillar Momentum"), use_container_width=True)

    # --- TIER 2: FORENSIC DEEP-DIVE ---
    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Censorship Delta by Research Pillar")
        fig_delta = px.box(filtered_df, x='Research_Pillar', y='Censorship_Delta', color='Research_Pillar', title="Editorial Pressure by Topic")
        st.plotly_chart(fig_delta, use_container_width=True)
    with col_b:
        st.subheader("Pillar-Specific Tone vs. Anxiety")
        st.plotly_chart(px.scatter(filtered_df, x="Literal_Text_Score", y="Subtext_Gravity_Score", color="Research_Pillar", hover_data=['SourceCommonName']), use_container_width=True)

    # --- TIER 3: FORENSIC ENGINE ---
    st.divider()
    st.header("🧬 Forensic Psycholinguistic Engine")
    forensic_metrics = ["S_Anger", "S_Anxiety", "S_Complexity", "S_Tentative", "S_ActRef"]
    avg_metrics = filtered_df.groupby('Research_Pillar')[forensic_metrics].mean().reset_index().melt(id_vars='Research_Pillar')
    st.plotly_chart(px.line_polar(avg_metrics, r='value', theta='variable', color='Research_Pillar', line_close=True), use_container_width=True)

    # --- 6. VISION-PROXY AI INTELLIGENCE ---
    if st.button("📝 Generate Pillar-Aware Forensic Report"):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            
            analysis_payload = {
                "Pillar_Volumes": filtered_df['Research_Pillar'].value_counts().to_dict(),
                "Censorship_Per_Pillar": filtered_df.groupby('Research_Pillar')['Censorship_Delta'].mean().to_dict(),
                "Forensic_Averages": filtered_df[forensic_metrics].mean().to_dict()
            }
            
            prompt = f"""
            Analyze this Pillar-filtered TNNM dataset: {analysis_payload}
            
            Address the following:
            1. Which Research Pillar shows the highest 'Suppression' momentum?
            2. Analyze the 'Media Influence' pillar regarding RSS and Confucius Institute narratives.
            3. Interpret the terminology shift in 'Geographic Identity' (Tibet vs Xizang).
            4. Based on 'Border Infrastructure' scores, is the narrative regarding Gyirong/Kerung securitized or normalized?
            """
            
            with st.spinner("Triangulating Pillar Data..."):
                st.markdown(f"### 🧬 Pillar-Specific Forensic Insights\n{model.generate_content(prompt).text}")
        except Exception as e:
            st.error(f"AI Error: {e}")
else:
    st.info("Upload TNNM Corpus to initiate automated gating and pillar classification.")
