import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import date
from pathlib import Path

# ----------------------------
# Helper: Custom Metric Sorting
# ----------------------------
def metric_sort_key(metric_name: str):
    """
    Custom key function to sort metrics in bureaucratic order (e.g., A. 1., A. 2., B. 6.)
    """
    match = re.match(r'([A-E])[\.\s]*(\d+(\.\d+)?)?', str(metric_name))

    if match:
        main_letter = match.group(1)
        main_number_str = match.group(2)

        primary_sort = main_letter
        secondary_sort = 0.0
        tertiary_sort = 0

        if main_number_str:
            try:
                secondary_sort = float(main_number_str)
            except ValueError:
                secondary_sort = 999.0

        # sub-sorting for a/b variants
        metric_lower = str(metric_name).lower()
        if 'a.' in metric_lower or ' a ' in metric_lower:
            tertiary_sort = 1
        elif 'b.' in metric_lower or ' b ' in metric_lower:
            tertiary_sort = 2

        return (primary_sort, secondary_sort, tertiary_sort)

    if metric_name == "E. Net General Relief Expenditure":
        return ('E', 999.0, 0)

    if metric_name in ["Date_Code", "County_Name", "County_Code", "Report_Month"]:
        return ('@', 0.0, 0)

    return ('Z', 0.0, 0)


# ----------------------------
# Config
# ----------------------------
st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------
# File List (fallback if not uploading)
# ----------------------------
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

# ----------------------------
# Cached data prep (NO st.* calls inside!)
# ----------------------------
@st.cache_data
def prepare_and_combine_gr_data(file_paths: tuple[str, ...]) -> tuple[pd.DataFrame, list[str]]:
    """
    Loads, cleans, and combines multiple GR data files into a single long-format DataFrame.

    Returns:
        (df_combined, logs)
    """
    logs: list[str] = []
    all_data_frames: list[pd.DataFrame] = []

    DATE_FORMATS_TO_TRY = [
        None,     # Pandas auto-detection
        '%Y-%m',  # 2015-07
        '%m/%Y',  # 07/2015
    ]

    # Mapping based on visual inspection of header row (header=4)
    column_index_map = {
        # Identifiers
        0: "Date_Code",
        1: "County_Name",
        3: "County_Code",
        6: "Report_Month",

        # Part A. Caseload
        7: "A. Adjustment",
        8: "A. 1. Cases brought forward",
        9: "A. 2. Cases added during month",
        10: "A. 3. Total cases available",
        11: "A. 4. Cases discontinued",
        12: "A. 5. Cases carried forward",

        # Part B - A. CASES
        13: "B. 6. Total General Relief Cases",
        14: "B. 6a. Family Cases",
        15: "B. 6b. One-person Cases",

        # Part B - B. PERSONS
        16: "B. 6. Total General Relief Persons",
        17: "B. 6a. Family Persons",
        18: "B. 6b. One-person Persons",

        # Part B - C. AMOUNT
        19: "B. 6. Total GR Expenditure",
        20: "B. 6(1). Amount in Cash",
        21: "B. 6(2). Amount in Kind",
        22: "B. 6a. Family Amount",
        23: "B. 6b. One-person Amount",

        # Part C
        24: "C. 7. Cases added during month (IA)",
        25: "C. 8. Total SSA checks disposed of",
        26: "C. 8a. Disposed within 1-10 days",
        27: "C. 9. SSA sent SSI/SSP check directly",
        28: "C. 10. Denial notice received",

        # Part D
        29: "D. 11. Reimbursements Cases",
        30: "D. 11a. SSA check received Cases",
        31: "D. 11b. Repaid by recipient Cases",
        32: "D. 11. Reimbursements Amount",
        33: "D. 11a. SSA check received Amount",
        34: "D. 11b. Repaid by recipient Amount",

        # Part E
        35: "E. Net General Relief Expenditure",
    }

    # Metrics are everything after the first 4 identifiers in the mapped values
    metric_cols = list(column_index_map.values())[4:]

    for path_str in file_paths:
        path = Path(path_str)
        if not path.exists():
            logs.append(f"⚠️ Missing file: {path_str} (skipped)")
            continue

        try:
            df = pd.read_csv(path, header=4)

            # Rename columns by POSITION (not by original names)
            df.columns = [column_index_map.get(i, col) for i, col in enumerate(df.columns)]

            # Keep only mapped columns that exist
            cols_to_keep = [name for name in column_index_map.values() if name in df.columns]
            df = df[cols_to_keep].copy()

            # Basic cleaning
            if "County_Name" in df.columns:
                df = df[df["County_Name"] != "Statewide"].copy()
                df = df.dropna(subset=["County_Name"])
                df["County_Name"] = df["County_Name"].astype(str).str.strip()

                # Drop rows where County_Name is purely numeric
                numeric_mask = df["County_Name"].str.match(r'^\d+(\.\d+)?$')
                df = df[~numeric_mask].copy()

            # --- Date parsing (robust) ---
            df["Date"] = pd.NaT
            parsed_any = False

            # Attempt 1: Report_Month
            if "Report_Month" in df.columns:
                report_month = df["Report_Month"].astype(str).str.strip()

                # 1a. Handle numeric YYYYMM (e.g., 201507.0)
                try:
                    cleaned = report_month.astype(float)
                    idx = cleaned.dropna().index
                    cleaned_int_str = cleaned.loc[idx].astype(int).astype(str)
                    df.loc[idx, "Date"] = pd.to_datetime(cleaned_int_str, format="%Y%m", errors="coerce")
                    if df["Date"].notna().any():
                        parsed_any = True
                except Exception:
                    pass

                # 1b. Try common formats
                for fmt in DATE_FORMATS_TO_TRY:
                    df["Date"] = df["Date"].fillna(pd.to_datetime(report_month, format=fmt, errors="coerce"))
                    if df["Date"].notna().any():
                        parsed_any = True

            # Attempt 2: Date_Code like Jun16 (fallback)
            if "Date_Code" in df.columns:
                date_code = df["Date_Code"].astype(str).str.strip().str.upper()
                df["Date"] = df["Date"].fillna(pd.to_datetime(date_code, format="%b%y", errors="coerce"))
                if df["Date"].notna().any():
                    parsed_any = True

            if not parsed_any or df["Date"].isna().all():
                logs.append(f"⚠️ Unparsable dates in: {path.name} (skipped)")
                continue

            df = df.dropna(subset=["Date"]).copy()

            # Numeric coercion for metric columns that exist
            for col in metric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # Drop rows where all metrics are NaN (only among metrics that exist)
            existing_metric_cols = [c for c in metric_cols if c in df.columns]
            if existing_metric_cols:
                df = df.dropna(subset=existing_metric_cols, how="all").copy()

            # Melt to long format
            id_vars = [c for c in ["Date", "Report_Month", "County_Name", "County_Code"] if c in df.columns]
            df_long = pd.melt(
                df,
                id_vars=id_vars,
                value_vars=existing_metric_cols,
                var_name="Metric",
                value_name="Value",
            )

            all_data_frames.append(df_long)
            logs.append(f"✅ Loaded: {path.name} ({len(df_long):,} long rows)")

        except Exception as e:
            logs.append(f"❌ Error processing {path.name}: {e}")

    if not all_data_frames:
        return pd.DataFrame(), logs

    df_combined = pd.concat(all_data_frames, ignore_index=True)
    df_combined = df_combined.sort_values("Date").reset_index(drop=True)

    # De-dupe on key fields
    key_cols = [c for c in ["Date", "County_Name", "Metric"] if c in df_combined.columns]
    if key_cols:
        df_combined = df_combined.drop_duplicates(subset=key_cols, keep="first")

    return df_combined, logs


# ----------------------------
# Sidebar: Upload OR use local files
# ----------------------------
st.sidebar.header("Data Source")

uploaded_files = st.sidebar.file_uploader(
    "Upload one or more GR CSVs (recommended)",
    type=["csv"],
    accept_multiple_files=True
)

resolved_paths: list[str] = []

if uploaded_files:
    # Save uploads to a temp folder so pandas can read by path and cache can key on paths
    upload_dir = Path("uploaded_gr_data")
    upload_dir.mkdir(exist_ok=True)
    for uf in uploaded_files:
        out_path = upload_dir / uf.name
        out_path.write_bytes(uf.getbuffer())
        resolved_paths.append(str(out_path))
else:
    # Fallback: look in script dir and /mnt/data (common in hosted envs)
    script_dir = Path(__file__).parent if "__file__" in globals() else Path.cwd()
    for name in GR_FILE_NAMES:
        p1 = script_dir / name
        p2 = Path("/mnt/data") / name
        if p1.exists():
            resolved_paths.append(str(p1))
        elif p2.exists():
            resolved_paths.append(str(p2))
        else:
            # keep the name anyway so logs show missing
            resolved_paths.append(str(p1))


# ----------------------------
# Run combination
# ----------------------------
data, load_logs = prepare_and_combine_gr_data(tuple(resolved_paths))

# ----------------------------
# Debug / Load status
# ----------------------------
st.header("🔍 Data Loading Check")

with st.expander("Show load log"):
    for line in load_logs:
        st.write(line)

if not isinstance(data, pd.DataFrame):
    st.error(f"FATAL ERROR: Data prep returned {type(data)} not a pandas.DataFrame.")
    st.stop()

if data.empty:
    st.error(
        "The combined DataFrame is EMPTY.\n\n"
        "Most likely: your CSVs aren’t present in the app environment. "
        "Use the sidebar uploader to add the files (or deploy them alongside the app)."
    )
    st.stop()

if "County_Name" not in data.columns:
    st.error(f"FATAL COLUMN ERROR: 'County_Name' missing. Found: {data.columns.tolist()}")
    st.stop()

st.success(f"Data Loaded successfully: {len(data):,} rows and {len(data.columns)} columns.")


# ----------------------------
# Build selector lists
# ----------------------------
all_counties = sorted(data["County_Name"].dropna().unique().tolist())
metric_categories = data["Metric"].dropna().unique().tolist()
metric_categories = sorted(metric_categories, key=metric_sort_key)


# ----------------------------
# Sidebar filters
# ----------------------------
st.sidebar.header("Filter Options")

min_date = data["Date"].min().to_pydatetime().date() if not data.empty else date(2015, 1, 1)
max_date = data["Date"].max().to_pydatetime().date() if not data.empty else date(2025, 12, 31)

default_start = date(2017, 1, 1)
default_end = date(2019, 12, 31)

start_date = max(min_date, default_start)
end_date = min(max_date, default_end)

if max_date < default_start or min_date > default_end:
    start_date = min_date
    end_date = max_date

date_range = st.sidebar.slider(
    "Select Date Range (Defaults to 2017-2019):",
    min_value=min_date,
    max_value=max_date,
    value=(start_date, end_date),
    format="YYYY/MM/DD",
)

data_dated = data[
    (data["Date"].dt.date >= date_range[0]) &
    (data["Date"].dt.date <= date_range[1])
].copy()

selected_counties = st.sidebar.multiselect(
    "Select County(s):",
    options=all_counties,
    default=["Alameda", "Fresno"] if {"Alameda", "Fresno"}.issubset(set(all_counties)) else all_counties[:2],
)

st.sidebar.subheader("Select Metric(s) to Overlay")
selected_metrics = st.sidebar.multiselect(
    "Select Metric(s):",
    options=metric_categories,
    default=["B. 6. Total General Relief Cases"] if "B. 6. Total General Relief Cases" in metric_categories else metric_categories[:1],
)


# ----------------------------
# Main UI
# ----------------------------
st.title("GR 237: General Relief")
st.markdown("Use the sidebar filters to compare multiple counties and multiple metrics on the chart below.")

if not selected_counties or not selected_metrics:
    st.info("Please select at least one county and one metric from the sidebar.")
    st.stop()

df_filtered = data_dated[
    data_dated["County_Name"].isin(selected_counties) &
    data_dated["Metric"].isin(selected_metrics)
].copy()

df_filtered = df_filtered.dropna(subset=["Value"])

# ----------------------------
# Visualization
# ----------------------------
if df_filtered.empty:
    st.warning("No data found for the selected combination of counties, metrics, and date range.")
else:
    df_filtered["County_Metric"] = df_filtered["County_Name"] + " - " + df_filtered["Metric"]
    y_title = "Value (Cases, Persons, or Expenditures)"

    base = alt.Chart(df_filtered).encode(
        x=alt.X("Date:T", axis=alt.Axis(title="Report Month", format="%b %Y")),
        y=alt.Y("Value:Q", title=y_title, scale=alt.Scale(zero=False)),
        color=alt.Color("County_Metric:N", legend=alt.Legend(title="Series")),
        tooltip=[
            alt.Tooltip("Date:T", title="Date", format="%b %Y"),
            alt.Tooltip("Report_Month:N"),
            alt.Tooltip("County_Name:N"),
            alt.Tooltip("Metric:N"),
            alt.Tooltip("Value:Q", format=",.0f"),
        ],
    ).properties(
        title=f"Interactive GR Database: {date_range[0].strftime('%Y/%m/%d')} to {date_range[1].strftime('%Y/%m/%d')}"
    ).interactive()

    st.altair_chart(base.mark_line(point=True), use_container_width=True)

# ----------------------------
# Underlying data
# ----------------------------
st.markdown("---")
st.subheader("📊 Underlying Filtered Data")

df_display = df_filtered.drop(columns=["County_Metric"], errors="ignore").copy()
df_display.rename(columns={"Value": "Value (Cases/Persons/Amount)"}, inplace=True)
st.dataframe(df_display)
