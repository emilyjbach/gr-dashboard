import streamlit as st
import pandas as pd
import altair as alt
import os


GR_FILE_NAMES = [
    "15-16.csv",
    "16-17.csv",
    "17-18.csv",
    "18-19.csv",
    "19-20.csv",
    "20-21.csv",
    "21-22.csv",
    "22-23.csv",
    "23-24.csv",
    "24-25.csv",
]
# config
st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded"
)

# data prep (moved inside system)
@st.cache_data
def prepare_and_combine_gr_data(file_names):
    """
    Loads, cleans, and combines multiple GR data files into a single long-format DataFrame.
    This heavy operation is run only once thanks to st.cache_data.
    """
    st.info(f"Combining {len(file_names)} GR data files...")
    all_data_frames = []

    # Mapping based on the visual inspection of the file headers (index 4)
    column_index_map = {
        # Identifiers
        0: "Date_Code",
        1: "County_Name",
        3: "County_Code",
        6: "Report_Month",

        # Part A. Caseload (GENERAL RELIEF AND INTERIM ASSISTANCE)
        7: "A. Adjustment",
        8: "A. 1. Cases brought forward",
        9: "A. 2. Cases added during month",
        10: "A. 3. Total cases available",
        11: "A. 4. Cases discontinued",
        12: "A. 5. Cases carried forward",

        # Part B. Caseload and Expenditures - A. CASES
        13: "B. 6. Total General Relief Cases",
        14: "B. 6a. Family Cases",
        15: "B. 6b. One-person Cases",

        # Part B. Caseload and Expenditures - B. PERSONS
        16: "B. 6. Total General Relief Persons",
        17: "B. 6a. Family Persons",
        18: "B. 6b. One-person Persons",

        # Part B. Caseload and Expenditures - C. AMOUNT
        19: "B. 6. Total GR Expenditure",
        20: "B. 6(1). Amount in Cash",
        21: "B. 6(2). Amount in Kind",
        22: "B. 6a. Family Amount",
        23: "B. 6b. One-person Amount",

        # Part C. SSI/SSP Interim Assistance
        24: "C. 7. Cases added during month (IA)",
        25: "C. 8. Total SSA checks disposed of",
        26: "C. 8a. Disposed within 1-10 days",
        27: "C. 9. SSA sent SSI/SSP check directly",
        28: "C. 10. Denial notice received",

        # Part D. Reimbursements
        29: "D. 11. Reimbursements Cases",
        30: "D. 11a. SSA check received Cases",
        31: "D. 11b. Repaid by recipient Cases",
        32: "D. 11. Reimbursements Amount",
        33: "D. 11a. SSA check received Amount",
        34: "D. 11b. Repaid by recipient Amount",

        # Part E. Net General Relief Expenditures
        35: "E. Net General Relief Expenditure",
    }

    metric_cols = list(column_index_map.values())[4:]

    for file_name in file_names:
        if not os.path.exists(file_name):
            st.warning(f"File not found during combination: {file_name}. Skipping.")
            continue

        try:
            df = pd.read_csv(file_name, header=4)
            
            # Rename columns
            df.columns = [column_index_map.get(i, col) for i, col in enumerate(df.columns)]
            
            
            cols_to_keep = [name for name in column_index_map.values() if name in df.columns]
            df = df[cols_to_keep].copy()

            # data clean & prep
            df = df[df["County_Name"] != "Statewide"].copy()
            df = df.dropna(subset=['County_Name'])
            
            # CRITICAL FIX: Ensure County_Name is always a string to prevent TypeError on sorted()
            df['County_Name'] = df['County_Name'].astype(str)

            # dates fixer
            df['Date'] = pd.to_datetime(df['Report_Month'], errors='coerce')
            df = df.dropna(subset=['Date'])
            
            # num fixer
            for col in metric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df.dropna(subset=metric_cols, how='all')

            # melt!!!!
            id_vars = ['Date', 'Report_Month', 'County_Name', 'County_Code']
            existing_metric_cols = [col for col in metric_cols if col in df.columns]
            
            df_long = pd.melt(
                df,
                id_vars=id_vars,
                value_vars=existing_metric_cols,
                var_name='Metric',
                value_name='Value'
            )
            all_data_frames.append(df_long)

        except Exception as e:
            st.error(f"Error processing {file_name}: {e}")

    # comb dataframes
    if all_data_frames:
        df_combined = pd.concat(all_data_frames, ignore_index=True)
        df_combined = df_combined.sort_values('Date').reset_index(drop=True)
        df_combined = df_combined.drop_duplicates(subset=['Date', 'County_Name', 'Metric'], keep='first')
        return df_combined
    else:
        st.error("No data could be processed and combined. Check file names and structure.")
        return pd.DataFrame()

# run data combination 
data = prepare_and_combine_gr_data(GR_FILE_NAMES)

# --- DEBUGGING BLOCK (Now helps confirm the fix worked) ---
st.header("🔍 Data Loading Check")

if not isinstance(data, pd.DataFrame):
    st.error(f"FATAL ERROR: The data preparation function returned type: {type(data)}. Expected pandas.DataFrame.")
    st.stop()

if data.empty:
    st.error("The combined DataFrame is EMPTY. This means none of the CSV files were found or processed successfully. Check file names and deployment integrity.")
    st.stop()

if 'County_Name' not in data.columns:
    st.error(f"FATAL COLUMN ERROR: 'County_Name' column is missing! Found columns: {data.columns.tolist()}")
    st.stop()
    
st.success(f"Data Loaded Successfully: {len(data)} rows and {len(data.columns)} columns.")
# --- END DEBUGGING BLOCK ---


# get uq lists for selectors 
# This line should now succeed due to the .astype(str) fix
all_counties = sorted(data['County_Name'].unique().tolist())
metric_categories = data['Metric'].unique().tolist()

# sidebar filters
st.sidebar.header("Filter Options")

# county
selected_counties = st.sidebar.multiselect(
    "Select County(s):",
    options=all_counties,
    default=[
        "Alameda",
        "Fresno",
    ]
)

# metric
st.sidebar.subheader("Select Metric(s) to Overlay")
selected_metrics = st.sidebar.multiselect(
    "Select Metric(s):",
    options=metric_categories,
    default=[
        "B. 6. Total General Relief Cases", 
    ]
)

# user prompts
st.title("GR 237: General Relief")
st.markdown("Use the sidebar filters to compare multiple counties and multiple metrics on the chart below.")

# data filtering
if not selected_counties or not selected_metrics:
    st.info("Please select at least one county and one metric from the sidebar.")
    st.stop()

df_filtered = data[
    data['County_Name'].isin(selected_counties) &
    data['Metric'].isin(selected_metrics)
].copy()

df_filtered = df_filtered.dropna(subset=['Value'])

# viz
if df_filtered.empty:
    st.warning("No data found for the selected combination of counties and metrics.")
else:
    df_filtered['County_Metric'] = df_filtered['County_Name'] + ' - ' + df_filtered['Metric']
    y_title = "Value (Cases, Persons, or Expenditures)"

    base = alt.Chart(df_filtered).encode(
        x=alt.X('Date', axis=alt.Axis(title='Report Month', format="%b %Y")),
        y=alt.Y('Value', title=y_title, scale=alt.Scale(zero=False)),
        color='County_Metric',
        tooltip=['Report_Month', 'County_Name', 'Metric', alt.Tooltip('Value', format=',.0f')]
    ).properties(
        title="Interactive GR Database [EB DRAFT]"
    ).interactive() 

    line_chart = base.mark_line(point=True)

    st.altair_chart(line_chart, use_container_width=True)
