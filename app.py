import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date 

# --- Helper Function for Custom Metric Sorting ---
def metric_sort_key(metric_name):
    """
    Custom key function to sort metrics in bureaucratic order (e.g., A. 1., A. 2., B. 6.)
    """
    match = re.match(r'([A-E])[\.\s]*(\d+(\.\d+)?)?', metric_name)
    
    if match:
        main_letter = match.group(1)
        main_number_str = match.group(2)
        
        primary_sort = main_letter
        secondary_sort = 0
        tertiary_sort = 0 
        
        if main_number_str:
            try:
                secondary_sort = float(main_number_str)
            except ValueError:
                secondary_sort = 999 
        
        if 'a.' in metric_name or 'a ' in metric_name:
            tertiary_sort = 1
        elif 'b.' in metric_name or 'b ' in metric_name:
            tertiary_sort = 2
            
        return (primary_sort, secondary_sort, tertiary_sort)
    
    if metric_name == "E. Net General Relief Expenditure":
        return ('E', 999, 0)
    if metric_name in ["Date_Code", "County_Name", "County_Code", "Report_Month"]:
        return ('@', 0, 0) 
    
    return ('Z', 0, 0) 

# --- File List ---
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

# --- Data Preparation Function ---
@st.cache_data
def prepare_and_combine_gr_data(file_names):
    """
    Loads, cleans, and combines multiple GR data files into a single long-format DataFrame.
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
            
            # 1. Ensure County_Name is always a string
            df['County_Name'] = df['County_Name'].astype(str)
            
            # 2. Filter out rows where County_Name is purely numeric/looks like a number
            numeric_mask = df['County_Name'].str.match(r'^\d+(\.\d+)?$')
            df = df[~numeric_mask].copy()

            # dates fixer - NUCLEAR OPTION: Combine all date info and use inference
            df['Date'] = pd.NaT 
            parsed = False
            
            # 1. Use Date_Code (e.g., Jun16) as primary date source for older files
            if 'Date_Code' in df.columns:
                date_col_date_code = df['Date_Code'].astype(str).str.strip()
                
                # Use infer_datetime_format=True for highly resilient parsing of MonYY format
                df['Date'] = pd.to_datetime(date_col_date_code, errors='coerce', infer_datetime_format=True)
                
                if not df['Date'].isna().all():
                    parsed = True
                    # st.info(f"Successfully parsed dates in {file_name} using inference on Date_Code.")
            
            # 2. If Date_Code failed (or wasn't MonYY), try Report_Month (e.g., 2020-07)
            if not parsed or df['Date'].isna().any() and 'Report_Month' in df.columns:
                date_col_report_month = df['Report_Month'].astype(str).str.strip()
                
                # Fill any remaining NaT values with Report_Month parsed inferentially
                df['Date'] = df['Date'].fillna(
                    pd.to_datetime(date_col_report_month, errors='coerce', infer_datetime_format=True)
                )
                if not df['Date'].isna().all():
                    parsed = True
                    # if df['Date'].isna().any():
                        # st.info(f"Partial date parsing success in {file_name} using Report_Month inference.")

            # 3. Aggressive numeric cleaning (Final attempt, only for remaining NaT)
            # This handles cases like 201507.0 that might be missed above
            if df['Date'].isna().any() and 'Report_Month' in df.columns:
                 unparsed_mask = df['Date'].isna()
                 date_col_cleaned_numeric = df.loc[unparsed_mask, 'Report_Month'].astype(str).str.strip()
                 try:
                    date_col_cleaned = date_col_cleaned_numeric.astype(float).dropna().astype(int).astype(str)
                    df.loc[date_col_cleaned.index, 'Date'] = df.loc[date_col_cleaned.index, 'Date'].fillna(
                        pd.to_datetime(date_col_cleaned, format='%Y%m', errors='coerce')
                    )
                    if not df['Date'].isna().all():
                        parsed = True
                        
                 except Exception:
                     pass

            # Final check and skip logic
            if not parsed or df['Date'].isna().all():
                 # We suppress the warning here to prevent the repeated messages in Streamlit UI if the file is indeed unparseable
                 # st.warning(f"All date rows dropped from {file_name} due to unparsable date format.")
                 continue 
            
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

# --- DEBUGGING BLOCK ---
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
    
st.success(f"Data Loaded successfully: {len(data)} rows and {len(data.columns)} columns.")
# --- END DEBUGGING BLOCK ---


# get uq lists for selectors 
all_counties = sorted(data['County_Name'].unique().tolist())
metric_categories = data['Metric'].unique().tolist()

# Use custom sort key for metrics
metric_categories = sorted(metric_categories, key=metric_sort_key) 


# sidebar filters
st.sidebar.header("Filter Options")

# Date Range Filter 
min_date = data['Date'].min().to_pydatetime().date() if not data.empty else date(2015, 1, 1)
max_date = data['Date'].max().to_pydatetime().date() if not data.empty else date(2025, 12, 31)

# Default range focused on 2017-2019 for verification
default_start = date(2017, 1, 1)
default_end = date(2019, 12, 31)

# Set the slider value within the actual min/max data range
start_date = max(min_date, default_start)
end_date = min(max_date, default_end)

# If the loaded data is entirely outside the 2017-2019 window, adjust the default value
if max_date < default_start or min_date > default_end:
    start_date = min_date
    end_date = max_date


date_range = st.sidebar.slider(
    "Select Date Range (Defaults to 2017-2019):",
    min_value=min_date,
    max_value=max_date,
    value=(start_date, end_date),
    format="YYYY/MM/DD"
)

# Apply Date Filter to the data
data_dated = data[
    (data['Date'].dt.date >= date_range[0]) & 
    (data['Date'].dt.date <= date_range[1])
].copy()


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

# data filtering: APPLY FILTERS TO THE DATE-FILTERED DATA
if not selected_counties or not selected_metrics:
    st.info("Please select at least one county and one metric from the sidebar.")
    st.stop()

df_filtered = data_dated[
    data_dated['County_Name'].isin(selected_counties) &
    data_dated['Metric'].isin(selected_metrics)
].copy()

df_filtered = df_filtered.dropna(subset=['Value'])

# viz
if df_filtered.empty:
    st.warning("No data found for the selected combination of counties, metrics, and date range.")
else:
    df_filtered['County_Metric'] = df_filtered['County_Name'] + ' - ' + df_filtered['Metric']
    y_title = "Value (Cases, Persons, or Expenditures)"

    base = alt.Chart(df_filtered).encode(
        x=alt.X('Date', axis=alt.Axis(title='Report Month', format="%b %Y")),
        y=alt.Y('Value', title=y_title, scale=alt.Scale(zero=False)),
        color='County_Metric',
        tooltip=['Report_Month', 'County_Name', 'Metric', alt.Tooltip('Value', format=',.0f')]
    ).properties(
        title=f"Interactive GR Database: {date_range[0].strftime('%Y/%m/%d')} to {date_range[1].strftime('%Y/%m/%d')}"
    ).interactive() 

    line_chart = base.mark_line(point=True)

    st.altair_chart(line_chart, use_container_width=True)

# --- UNDERLYING DATA ---
st.markdown("---")
st.subheader("📊 Underlying Filtered Data")

df_display = df_filtered.drop(columns=['County_Metric']).copy()

df_display.rename(columns={'Value': 'Value (Cases/Persons/Amount)'}, inplace=True)

st.dataframe(df_display)
