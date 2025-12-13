import streamlit as st
import pandas as pd
import altair as alt

# --- Configuration ---
st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Data Loading Function ---
@st.cache_data
def load_data(file_path):
    """
    Loads the prepared data from CSV. 
    Using st.cache_data ensures the data is loaded only once, 
    making the deployed app faster and more stable.
    """
    df = pd.read_csv(file_path)
    # Ensure Date is in datetime format for chronological sorting
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Ensure 'Report_Month' exists and is formatted correctly for tooltips/display
    df['Report_Month'] = df['Date'].dt.strftime('%b %Y')
    return df

# Load the prepared data file
DATA_FILE = "gr_data_prepared.csv"
try:
    # This file MUST be present in the same GitHub repository folder as this script.
    data = load_data(DATA_FILE)
except FileNotFoundError:
    st.error(f"Error: Data file '{DATA_FILE}' not found.")
    st.info("Please ensure 'gr_data_prepared.csv' is committed and pushed to your GitHub repository.")
    st.stop()

# Get unique lists for selectors
all_counties = sorted(data['County_Name'].unique().tolist())
all_metrics = data['Metric'].unique().tolist()

# --- Sidebar Filters ---
st.sidebar.header("Filter Options")

# 1. County Selection
selected_counties = st.sidebar.multiselect(
    "Select County(s):",
    options=all_counties,
    default=all_counties[:3] # Default to the first three counties
)

# 2. Metric Selection
selected_metrics = st.sidebar.multiselect(
    "Select Metric(s) to Overlay:",
    options=all_metrics,
    default=all_metrics
)

# --- Main Application Content ---
st.title("General Relief (GR) Monthly Caseload and Expenditure Trends")

# --- Data Filtering ---
if not selected_counties or not selected_metrics:
    st.info("Please select at least one county and one metric from the sidebar.")
    st.stop()

# Filter the data based on user selections
df_filtered = data[
    data['County_Name'].isin(selected_counties) &
    data['Metric'].isin(selected_metrics)
].copy()

# Drop rows where 'Value' is NaN 
df_filtered = df_filtered.dropna(subset=['Value'])

# --- Visualization ---

if df_filtered.empty:
    st.warning("No data found for the selected combination of counties and metrics.")
else:
    # Create a combined column for color/legend to allow overlay of both county and metric
    df_filtered['County_Metric'] = df_filtered['County_Name'] + ' - ' + df_filtered['Metric']

    # Base chart setup
    base = alt.Chart(df_filtered).encode(
        # X-axis is the date, sorted chronologically
        x=alt.X('Date', axis=alt.Axis(title='Report Month', format="%Y-%m")),
        # Y-axis is the value
        y=alt.Y('Value', title='Value (Cases or Expenditures)', scale=alt.Scale(zero=False)),
        # Color encoding combines both county and metric for overlaying
        color='County_Metric',
        tooltip=['Report_Month', 'County_Name', 'Metric', alt.Tooltip('Value', format=',.0f')]
    ).properties(
        title="GR Trends: Cases and Expenditures Over Time"
    ).interactive() # Allows for zooming and panning

    # Line Chart Layer
    line_chart = base.mark_line(point=True)

    st.altair_chart(line_chart, use_container_width=True)

    st.markdown("---")
    st.subheader("Raw Data Preview")
    st.dataframe(df_filtered[['Report_Month', 'County_Name', 'Metric', 'Value']].reset_index(drop=True))

    # --- Metrics Legend ---
    st.sidebar.markdown("### Metric Definitions")
    st.sidebar.markdown(
        """
        - **Total GR Cases**: Total General Relief Cases 
        - **One-person Cases**: General Relief One-person cases 
        - **Total GR Expenditure**: Total General Relief Expenditures 
        - **Net GR Expenditure**: Net General Relief Expenditure 
        """
    )
