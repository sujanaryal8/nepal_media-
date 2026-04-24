import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import google.generativeai as gemini
import requests
from transformers import pipeline

# Database setup
def init_db():
    conn = sqlite3.connect("nepal_media.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_data (
            GKGRECORDID TEXT PRIMARY KEY,
            DATE TEXT,
            PUBLISHER TEXT,
            GCAM TEXT,
            CONTENT TEXT
        )
    """)
    conn.commit()
    return conn

# Check for existing data
def check_existing_data(conn, data):
    cursor = conn.cursor()
    existing_ids = set(row[0] for row in cursor.execute("SELECT GKGRECORDID FROM media_data"))
    new_data = data[~data['GKGRECORDID'].isin(existing_ids)]
    return new_data

# Insert new data into the database
def insert_data(conn, data):
    cursor = conn.cursor()
    for _, row in data.iterrows():
        cursor.execute("""
            INSERT OR IGNORE INTO media_data (GKGRECORDID, DATE, PUBLISHER, GCAM, CONTENT)
            VALUES (?, ?, ?, ?, ?)
        """, (row['GKGRECORDID'], row['DATE'], row['PUBLISHER'], row['GCAM'], row['CONTENT']))
    conn.commit()

# NLP and Sentiment Analysis
def extract_tone(gcam):
    return float(gcam.split(',')[0]) if gcam else None

def extract_anxiety(gcam):
    return float(gcam.split(',')[2]) if gcam else None

# Keyword Search
def count_keywords(content, keywords):
    if isinstance(keywords, str):
        keywords = [keywords]
    return sum(content.lower().count(keyword.lower()) for keyword in keywords)

# Validate uploaded data
def validate_data(data):
    required_columns = ['GKGRECORDID', 'DATE', 'PUBLISHER', 'GCAM', 'CONTENT']
    missing_columns = [col for col in required_columns if col not in data.columns]
    if missing_columns:
        return False, missing_columns
    return True, []

# Streamlit App
st.title("Nepali Media Analysis Dashboard")

# Sidebar for file upload and keyword input
st.sidebar.header("Upload Data")
file = st.sidebar.file_uploader("Upload File (CSV, XLSX, XLS)", type=["csv", "xlsx", "xls"])

# Read file based on type
if file:
    try:
        if file.name.endswith('.csv'):
            data = pd.read_csv(file)
        elif file.name.endswith(('.xlsx', '.xls')):
            data = pd.read_excel(file)
        else:
            st.sidebar.error("Unsupported file format. Please upload a CSV, XLSX, or XLS file.")
            data = None

        if data is not None:
            # Validate uploaded data
            is_valid, missing_columns = validate_data(data)
            if not is_valid:
                st.sidebar.error(f"Uploaded file is missing required columns: {', '.join(missing_columns)}")
            else:
                new_data = check_existing_data(conn, data)
                if not new_data.empty:
                    insert_data(conn, new_data)
                    st.sidebar.success(f"Inserted {len(new_data)} new rows into the database.")
                else:
                    st.sidebar.info("No new data to insert.")
    except Exception as e:
        st.sidebar.error(f"An error occurred while processing the file: {e}")

# Initialize database
conn = init_db()

# Keyword Configuration
st.sidebar.header("Keyword Configuration")
amplify_keywords = st.sidebar.text_area("Amplify Keywords", "development, harmony, one-china, infrastructure").split(',')
normalize_keywords = st.sidebar.text_area("Normalize Keywords", "xizang, partnership, neighbor, strategic").split(',')
resist_keywords = st.sidebar.text_area("Resist Keywords", "rights, arrest, border, dispute, suppression").split(',')
relevant_keywords = st.sidebar.text_area("Relevant Keywords", "tibet, buddhism, dalai lama, lhasa").split(',')

# Load NLP models
@st.cache_resource
def load_nlp_models():
    sentiment_analyzer = pipeline("sentiment-analysis")
    return sentiment_analyzer

# Perform sentiment analysis
def perform_sentiment_analysis(content, sentiment_analyzer):
    try:
        result = sentiment_analyzer(content[:512])  # Limit to 512 characters for processing
        if result:
            return result[0]['label'], result[0]['score']
        else:
            return None, None
    except Exception as e:
        st.error(f"Error in sentiment analysis: {e}")
        return None, None

# Load NLP models
sentiment_analyzer = load_nlp_models()

# Perform sentiment analysis on the data
data['Sentiment_Label'], data['Sentiment_Score'] = zip(*data['CONTENT'].apply(lambda x: perform_sentiment_analysis(x, sentiment_analyzer)))

# Fetch data from the database
data = pd.read_sql_query("SELECT * FROM media_data", conn)
data['Tone'] = data['GCAM'].apply(extract_tone)
data['Anxiety'] = data['GCAM'].apply(extract_anxiety)

# Keyword Hit Count
st.sidebar.header("Keyword Hit Count")
st.sidebar.write(f"Amplify: {data['CONTENT'].apply(lambda x: count_keywords(x, amplify_keywords)).sum()}")
st.sidebar.write(f"Normalize: {data['CONTENT'].apply(lambda x: count_keywords(x, normalize_keywords)).sum()}")
st.sidebar.write(f"Resist: {data['CONTENT'].apply(lambda x: count_keywords(x, resist_keywords)).sum()}")
st.sidebar.write(f"Relevant: {data['CONTENT'].apply(lambda x: count_keywords(x, relevant_keywords)).sum()}")

# Methodology Section
st.header("Methodology")
st.markdown("""
- **Amplify**: Narratives aligning with PRC state positions on development and social stability.
- **Normalize**: Framing that encourages the adoption of PRC terminology (e.g., Xizang) and bilateral strategic necessity.
- **Resist**: Content highlighting human rights, border friction, or religious suppression.
- **Relevant**: The baseline corpus of articles specifically discussing Tibet or Buddhism.
""")

# Visualizations
st.header("Visualizations")

# Narrative Trajectory
st.subheader("Narrative Trajectory")
data['Year'] = pd.to_datetime(data['DATE']).dt.year
trajectory = data.groupby(['Year']).size().reset_index(name='Count')
fig = px.line(trajectory, x='Year', y='Count', title='Narrative Trajectory (2015-2025)')
st.plotly_chart(fig)

# Sentiment Scatter
st.subheader("Sentiment Scatter")
fig = px.scatter(data, x='Tone', y='Anxiety', color='PUBLISHER', title='Tone vs. Anxiety by Publisher')
st.plotly_chart(fig)

# Terminology Tracker
st.subheader("Terminology Tracker")
data['Tibet_Count'] = data['CONTENT'].str.count("Tibet")
data['Xizang_Count'] = data['CONTENT'].str.count("Xizang")
terminology = data[['Tibet_Count', 'Xizang_Count']].sum().reset_index()
terminology.columns = ['Term', 'Count']
fig = px.bar(terminology, x='Term', y='Count', title='Tibet vs. Xizang Usage')
st.plotly_chart(fig)

# Policy Brief Generation
st.header("Policy Brief")
if st.button("Generate Policy Brief"):
    gemini.configure(api_key="YOUR_API_KEY")
    prompt = "Generate a policy brief based on the analysis of Nepali media data."
    response = gemini.generate(prompt=prompt)
    st.write(response)

# GDELT Integration
def fetch_gdelt_data(keywords, start_date, end_date):
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    query_params = {
        "query": " OR ".join(keywords),  # Combine keywords with OR for GDELT query
        "mode": "ArtList",
        "format": "CSV",
        "startdatetime": start_date.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end_date.strftime("%Y%m%d%H%M%S"),
        "maxrecords": 250,
        "sort": "DateDesc"
    }

    response = requests.get(base_url, params=query_params)
    if response.status_code == 200:
        data = pd.read_csv(pd.compat.StringIO(response.text))
        return data
    else:
        st.error("Failed to fetch data from GDELT API. Please try again later.")
        return pd.DataFrame()

# Add GDELT data collection to the dashboard
st.sidebar.header("GDELT Data Collection")
start_date = st.sidebar.date_input("Start Date", value=pd.to_datetime("2015-01-01"))
end_date = st.sidebar.date_input("End Date", value=pd.to_datetime("2026-12-31"))
gdelt_keywords = st.sidebar.text_area("GDELT Keywords", "Tibet, Buddhism, China").split(',')

if st.sidebar.button("Fetch GDELT Data"):
    gdelt_data = fetch_gdelt_data(gdelt_keywords, start_date, end_date)
    if not gdelt_data.empty:
        st.write("Fetched GDELT Data:")
        st.dataframe(gdelt_data)
        # Insert GDELT data into the database
        new_data = check_existing_data(conn, gdelt_data)
        if not new_data.empty:
            insert_data(conn, new_data)
            st.sidebar.success(f"Inserted {len(new_data)} new rows from GDELT into the database.")
        else:
            st.sidebar.info("No new data to insert from GDELT.")