import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date

# ----------------------------
# Helper: metric sorting (safe)
# ----------------------------
def metric_sort_key(metric_name):
    name = str(metric_name)

    m = re.match(r"^\s*([A-E])", name)
    letter = m.group(1) if m else "Z"

    n = re.search(r"(\d+)", name)
    number = int(n.group(1)) if n else 0

    lower = name.lower()
    sub = 0
    if ("a." in lower) or (" a " in lower):
        sub = 1
    elif ("b." in lower) or (" b " in lower):
        sub = 2

    return (letter, number, sub)


# ----------------------------
# File List
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
# Streamlit config
# ----------------------------
st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------
# Data Preparation (FIX: do NOT drop older years)
# Key fixes:
# 1) resolve paths in /mnt/data too
# 2) robust Date_Code + Report_Month parsing (many formats)
# 3) NEVER call dropna(subset=metric_cols) if some metric_cols are missing
#    -> use existing_metric_cols instead (this is what was skipping 2015-2019)
# 4) melt id_vars only if columns exist
# ----------------------------
@st.cache_data
def prepare_and_combine_gr_data(file_names):
    all_data_frames = []
    logs = []

    # Many GR files vary in how months are encoded; we try a broad set.
    DATE_FORMATS_TO_TRY = [
        None,           # pandas auto (YYYY-MM-DD, etc.)
        "%Y%m",         # 201507
        "%Y-%m",        # 2015-07
        "%Y-%m-%d",     # 2015-07-01
        "%m/%Y",        # 07/2015
        "%m/%d/%Y",     # 07/01/2015
        "%b%y",         # Jul15
        "%b-%y",        # Jul-15
        "%b %y",        # Jul 15
    ]

    column_index_map = {
        0: "Date_Code",
        1: "County_Name",
        3: "County_Code",
        6: "Report_Month",

        7: "A. Adjustment",
        8: "A. 1. Cases brought forward",
        9: "A. 2. Cases added during month",
        10: "A. 3. Total cases available",
        11: "A. 4. Cases discontinued",
        12: "A. 5. Cases carried forward",

        13: "B. 6. Total General Relief Cases",
        14: "B. 6a. Family Cases",
        15: "B. 6b. One-person Cases",

        16: "B. 6. Total General Relief Persons",
        17: "B. 6a. Family Persons",
        18: "B. 6b. One-person Persons",

        19: "B. 6. Total GR Expenditure",
        20: "B. 6(1). Amount in Cash",
        21: "B. 6(2). Amount in Kind",
        22: "B. 6a. Family Amount",
        23: "B. 6b. One-person Amount",

        24: "C. 7. Cases added during month (IA)",
        25: "C. 8. Total SSA checks disposed of",
        26: "C. 8a. Disposed within 1-10 days",
        27: "C. 9. SSA sent SSI/SSP check directly",
        28: "C. 10. Denial notice received",

        29: "D. 11. Reimbursements Cases",
        30: "D. 11a. SSA check received Cases",
        31: "D. 11b. Repaid by recipient Cases",
        32: "D. 11. Reimbursements Amount",
        33: "D. 11a. SSA check received Amount",
        34: "D. 11b. Repaid by recipient Amount",

        35: "E. Net General Relief Expenditure",
    }

    metric_cols_full = list(column_index_map.values())[4:]
    county_has_letter = re.compile(r"[A-Za-z]")

    def resolve_path(fname):
        if os.path.exists(fname):
            return fname
        alt_path = os.path.join("/mnt/data", fname)
        if os.path.exists(alt_path):
            return alt_path
        return None

    for file_name in file_names:
        path = resolve_path(file_name)
        if not path:
            logs.append("Missing file: " + str(file_name))
            continue

        try:
            df = pd.read_csv(path, header=4)

            # Rename columns by position
            df.columns = [column_index_map.get(i, col) for i, col in enumerate(df.columns)]

            # Keep only mapped columns that exist
            cols_to_keep = [c for c in column_index_map.values() if c in df.columns]
            df = df[cols_to_keep].copy()

            # Basic cleaning
            if "County_Name" not in df.columns:
                logs.append(file_name + ": missing County_Name after mapping")
                continue

            df = df[df["County_Name"] != "Statewide"].copy()
            df = df.dropna(subset=["County_Name"]).copy()
            df["County_Name"] = df["County_Name"].astype(str).str.strip()

            # Drop numeric-ish county rows, keep names that contain at least one letter
            numeric_mask = df["County_Name"].str.match(r"^\d+(\.\d+)?$")
            df = df[~numeric_mask].copy()
            df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()

            # ---- Date parsing ----
            df["Date"] = pd.NaT

            # Prefer Date_Code for older years if present
            if "Date_Code" in df.columns:
                dc_raw = df["Date_Code"].astype(str).str.strip()

                # If Date_Code sometimes numeric like 201507 or 201507.0
                dc_num = pd.to_numeric(dc_raw, errors="coerce")
                idx_num = dc_num.dropna().index
                if len(idx_num) > 0:
                    dc_yyyymm = dc_num.loc[idx_num].astype(int).astype(str)
                    parsed_dc_num = pd.to_datetime(dc_yyyymm, format="%Y%m", errors="coerce")
                    df.loc[idx_num, "Date"] = df.loc[idx_num, "Date"].fillna(parsed_dc_num)

                # Try several explicit formats then auto
                dc_up = dc_raw.str.upper()
                for fmt in ["%b%y", "%b-%y", "%b %y"]:
                    parsed_dc = pd.to_datetime(dc_up, format=fmt, errors="coerce")
                    df["Date"] = df["Date"].fillna(parsed_dc)

                df["Date"] = df["Date"].fillna(pd.to_datetime(dc_raw, errors="coerce"))

            # Then try Report_Month (newer years / fallback)
            if "Report_Month" in df.columns:
                rm_raw = df["Report_Month"].astype(str).str.strip()

                # Numeric YYYYMM (very common in older/newer mixed)
                rm_num = pd.to_numeric(rm_raw, errors="coerce")
                idx_rm = rm_num.dropna().index
                if len(idx_rm) > 0:
                    rm_yyyymm = rm_num.loc[idx_rm].astype(int).astype(str)
                    parsed_rm_num = pd.to_datetime(rm_yyyymm, format="%Y%m", errors="coerce")
                    df.loc[idx_rm, "Date"] = df.loc[idx_rm, "Date"].fillna(parsed_rm_num)

                # Try formats
                for fmt in DATE_FORMATS_TO_TRY:
                    parsed_rm = pd.to_datetime(rm_raw, format=fmt, errors="coerce")
                    df["Date"] = df["Date"].fillna(parsed_rm)

                # Final auto
                df["Date"] = df["Date"].fillna(pd.to_datetime(rm_raw, errors="coerce"))

            if df["Date"].notna().sum() == 0:
                logs.append(file_name + ": no parsable dates (skipped)")
                continue

            df = df.dropna(subset=["Date"]).copy()

            # ---- Metrics numeric coercion (only existing columns) ----
            existing_metric_cols = [c for c in metric_cols_full if c in df.columns]
            if len(existing_metric_cols) == 0:
                logs.append(file_name + ": no metric columns after mapping (skipped)")
                continue

            for col in existing_metric_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # CRITICAL FIX: dropna only on existing metrics (older files may have fewer cols)
            df = df.dropna(subset=existing_metric_cols, how="all").copy()
            if df.empty:
                logs.append(file_name + ": all metric values empty after coercion (skipped)")
                continue

            # ---- Melt (id_vars must exist) ----
            id_vars = []
            for c in ["Date", "Report_Month", "County_Name", "County_Code"]:
                if c in df.columns:
                    id_vars.append(c)

            df_long = pd.melt(
                df,
                id_vars=id_vars,
                value_vars=existing_metric_cols,
                var_name="Metric",
                value_name="Value",
            )

            all_data_frames.append(df_long)

            file_min = df["Date"].min().date()
            file_max = df["Date"].max().date()
            logs.append(file_name + ": loaded " + str(len(df_long)) + " rows (" + str(file_min) + " to " + str(file_max) + ")")

        except Exception as e:
            logs.append(file_name + ": error " + str(e))
            continue

    if len(all_data_frames) == 0:
        return pd.DataFrame(), logs

    df_combined = pd.concat(all_data_frames, ignore_index=True)
    df_combined = df_combined.sort_values("Date").reset_index(drop=True)
    df_combined = df_combined.drop_duplicates(subset=["Date", "County_Name", "Metric"], keep="first")
    return df_combined, logs


# ----------------------------
# Run load
# ----------------------------
data, load_logs = prepare_and_combine_gr_data(GR_FILE_NAMES)

st.header("🔍 Data Loading Check")
with st.expander("Show load log"):
    for line in load_logs:
        st.write(line)

if not isinstance(data, pd.DataFrame):
    st.error("FATAL: data loader did not return a DataFrame.")
    st.stop()

if data.empty:
    st.error("The combined DataFrame is EMPTY. Ensure the CSVs exist in the app directory or /mnt/data.")
    st.stop()

st.success("Data loaded successfully: " + str(len(data)) + " rows, " + str(len(data.columns)) + " columns.")
st.write("Overall date range: " + str(data["Date"].min().date()) + " to " + str(data["Date"].max().date()))

# ----------------------------
# Build selector lists
# ----------------------------
all_counties = sorted(data["County_Name"].unique().tolist())
metric_categories = sorted(data["Metric"].unique().tolist(), key=metric_sort_key)

# ----------------------------
# Sidebar filters
# ----------------------------
st.sidebar.header("Filter Options")

min_date = data["Date"].min().date()
max_date = data["Date"].max().date()

default_start = date(2017, 1, 1)
default_end = date(2019, 12, 31)

start_date = default_start if default_start >= min_date else min_date
end_date = default_end if default_end <= max_date else max_date
if (max_date < default_start) or (min_date > default_end):
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
    default=[c for c in ["Alameda", "Fresno"] if c in all_counties],
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

if (len(selected_counties) == 0) or (len(selected_metrics) == 0):
    st.info("Please select at least one county and one metric from the sidebar.")
    st.stop()

df_filtered = data_dated[
    data_dated["County_Name"].isin(selected_counties) &
    data_dated["Metric"].isin(selected_metrics)
].copy()

df_filtered = df_filtered.dropna(subset=["Value"]).copy()

# ----------------------------
# Visualization
# ----------------------------
if df_filtered.empty:
    st.warning("No data found for the selected combination of counties, metrics, and date range.")
else:
    df_filtered["County_Metric"] = df_filtered["County_Name"] + " - " + df_filtered["Metric"]

    base = alt.Chart(df_filtered).encode(
        x=alt.X("Date:T", axis=alt.Axis(title="Report Month", format="%b %Y")),
        y=alt.Y("Value:Q", title="Value (Cases, Persons, or Expenditures)", scale=alt.Scale(zero=False)),
        color=alt.Color("County_Metric:N"),
        tooltip=[
            alt.Tooltip("County_Name:N"),
            alt.Tooltip("Metric:N"),
            alt.Tooltip("Date:T", format="%b %Y"),
            alt.Tooltip("Value:Q", format=",.0f"),
        ],
    ).properties(
        title="Interactive GR Database: " + date_range[0].strftime("%Y/%m/%d") + " to " + date_range[1].strftime("%Y/%m/%d")
    ).interactive()

    st.altair_chart(base.mark_line(point=True), use_container_width=True)

# ----------------------------
# Underlying data
# ----------------------------
st.markdown("---")
st.subheader("📊 Underlying Filtered Data")

df_display = df_filtered.drop(columns=["County_Metric"], errors="ignore").copy()
df_display = df_display.rename(columns={"Value": "Value (Cases/Persons/Amount)"})
st.dataframe(df_display)
