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
    metric_name = str(metric_name)
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

        lower = metric_name.lower()
        if 'a.' in lower or ' a ' in lower:
            tertiary_sort = 1
        elif 'b.' in lower or ' b ' in lower:
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

    # IMPORTANT: No st.* UI calls inside cached function.

    all_data_frames = []

    # Expanded formats to ensure 2016/2017 parses properly across files
    DATE_FORMATS_TO_TRY = [
        None,           # Pandas auto-detection (YYYY-MM-DD, YYYY/MM/DD, etc.)
        '%Y-%m',        # 2015-07
        '%Y-%m-%d',     # 2019-07-01
        '%m/%Y',        # 07/2015
        '%m/%d/%Y',     # 07/01/2019
        '%b%y',         # Jun16
        '%b-%y',        # Jun-16
        '%b %y',        # Jun 16
    ]

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

    # County must contain at least one letter (prevents numeric garbage rows)
    county_has_letter = re.compile(r"[A-Za-z]")

    def resolve_path(name: str) -> str | None:
        # Look in working dir first, then /mnt/data (common in Streamlit deployments)
        if os.path.exists(name):
            return name
        alt_path = os.path.join("/mnt/data", name)
        if os.path.exists(alt_path):
            return alt_path
        return None

    for file_name in file_names:
        path = resolve_path(file_name)
        if not path:
            # Can't use st.warning in cache; just skip.
            continue

        try:
            df = pd.read_csv(path, header=4)

            # Rename columns by position
            df.columns = [column_index_map.get(i, col) for i, col in enumerate(df.columns)]

            cols_to_keep = [name for name in column_index_map.values() if name in df.columns]
            df = df[cols_to_keep].copy()

            # data clean & prep
            df = df[df["County_Name"] != "Statewide"].copy()
            df = df.dropna(subset=['County_Name'])

            # ensure County_Name is string
            df['County_Name'] = df['County_Name'].astype(str).str.strip()

            # drop numeric-looking counties AND anything without a letter
            numeric_mask = df['County_Name'].str.match(r'^\d+(\.\d+)?$')
            df = df[~numeric_mask].copy()
            df = df[df['County_Name'].apply(lambda x: bool(county_has_letter.search(x)))].copy()

            # ---- DATE PARSING (key fix to reach 2017) ----
            df['Date'] = pd.NaT

            # Attempt A: parse Report_Month in multiple ways (covers many files)
            if 'Report_Month' in df.columns:
                report_month_raw = df['Report_Month'].astype(str).str.strip()

                # A1: numeric YYYYMM (e.g., 201607.0 -> 201607)
                try:
                    cleaned_numeric = pd.to_numeric(report_month_raw, errors='coerce')
                    idx = cleaned_numeric.dropna().index
                    cleaned_yyyymm = cleaned_numeric.loc[idx].astype(int).astype(str)
                    df.loc[idx, 'Date'] = pd.to_datetime(cleaned_yyyymm, form
