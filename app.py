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
# Data Preparation
# Fix for 16-17.csv "no parsable dates":
# 1) try multiple header rows (some years shift)
# 2) if mapped Date_Code/Report_Month missing, fall back to raw column positions
# 3) try more date formats commonly seen in GR files
# ----------------------------
@st.cache_data
def prepare_and_combine_gr_data(file_names):
    all_data_frames = []
    logs = []

    DATE_FORMATS = [
        "%Y%m",         # 201607
        "%Y-%m",        # 2016-07
        "%Y-%m-%d",     # 2016-07-01
        "%m/%Y",        # 07/2016
        "%m/%d/%Y",     # 07/01/2016
        "%b%y",         # Jul16
        "%b-%y",        # Jul-16
        "%b %y",        # Jul 16
        "%b%Y",         # Jul2016
        "%b-%Y",        # Jul-2016
        "%b %Y",        # Jul 2016
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

    def try_read_csv(path):
        # Some GR years have a different number of preamble rows.
        # Try a few headers and take the first that yields a non-trivial frame.
        for h in [4, 5, 3, 0]:
            try:
                df0 = pd.read_csv(path, header=h)
                if isinstance(df0, pd.DataFrame) and df0.shape[1] >= 6 and df0.shape[0] >= 1:
                    return df0, h
            except Exception:
                pass
        return None, None

    def parse_date_series(series):
        s = series.astype(str).str.strip()

        # Normalize common junk:
        # - remove trailing ".0" from numeric-like strings
        # - remove extra spaces
        s = s.str.replace(r"\.0$", "", regex=True)
        s = s.str.replace(r"\s+", " ", regex=True)

        out = pd.Series(pd.NaT, index=s.index)

        # Numeric YYYYMM path
        num = pd.to_numeric(s, errors="coerce")
        idx = num.dropna().index
        if len(idx) > 0:
            yyyymm = num.loc[idx].astype(int).astype(str)
            out.loc[idx] = pd.to_datetime(yyyymm, format="%Y%m", errors="coerce")

        # Explicit formats
        for fmt in DATE_FORMATS:
            parsed = pd.to_datetime(s, format=fmt, errors="coerce")
            out = out.fillna(parsed)

        # Final auto-detect
        out = out.fillna(pd.to_datetime(s, errors="coerce"))
        return out

    for file_name in file_names:
        path = resolve_path(file_name)
        if not path:
            logs.append(file_name + ": missing file")
            continue

        df_raw, used_header = try_read_csv(path)
        if df_raw is None:
            logs.append(file_name + ": could not read csv")
            continue

        # Rename by index (your original approach)
        df = df_raw.copy()
        df.columns = [column_index_map.get(i, col) for i, col in enumerate(df.columns)]

        # Keep only known mapped columns that exist (but keep a copy of raw for fallbacks)
        cols_to_keep = [c for c in column_index_map.values() if c in df.columns]
        df = df[cols_to_keep].copy()

        if "County_Name" not in df.columns:
            # If mapping failed due to shifted columns, try to recover county by raw position 1
            try:
                df_raw_county = df_raw.iloc[:, 1]
                df["County_Name"] = df_raw_county
            except Exception:
                logs.append(file_name + ": County_Name missing after mapping (header=" + str(used_header) + ")")
                continue

        # County cleanup
        df = df[df["County_Name"] != "Statewide"].copy()
        df = df.dropna(subset=["County_Name"]).copy()
        df["County_Name"] = df["County_Name"].astype(str).str.strip()

        numeric_mask = df["County_Name"].str.match(r"^\d+(\.\d+)?$")
        df = df[~numeric_mask].copy()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()

        # ---- Date parsing with robust fallbacks ----
        df["Date"] = pd.NaT

        # Preferred: mapped columns if present
        candidates = []

        if "Date_Code" in df.columns:
            candidates.append(("Date_Code", df["Date_Code"]))
        if "Report_Month" in df.columns:
            candidates.append(("Report_Month", df["Report_Month"]))

        # Critical fallback for 16-17 when mapping shifts:
        # use raw col 0 (often Date_Code) and raw col 6 (often Report_Month) if they exist
        try:
            if df_raw.shape[1] >= 1:
                candidates.append(("RAW_COL0", df_raw.iloc[:, 0]))
        except Exception:
            pass
        try:
            if df_raw.shape[1] >= 7:
                candidates.append(("RAW_COL6", df_raw.iloc[:, 6]))
        except Exception:
            pass

        # Also try any raw columns whose header contains "month" or "date"
        try:
            for c in df_raw.columns:
                cstr = str(c).lower()
                if ("month" in cstr) or ("date" in cstr):
                    candidates.append(("RAW_NAME_" + str(c), df_raw[c]))
        except Exception:
            pass

        # Apply candidates until we get some dates
        for label, series in candidates:
            if df["Date"].notna().sum() > 0:
                break
            try:
                df["Date"] = df["Date"].fillna(parse_date_series(series))
            except Exception:
                continue

        if df["Date"].notna().sum() == 0:
            logs.append(file_name + ": no parsable dates (skipped) (header=" + str(used_header) + ")")
            continue

        df = df.dropna(subset=["Date"]).copy()

        # ---- Metrics (only existing) ----
        existing_metric_cols = [c for c in metric_cols_full if c in df.columns]
        if len(existing_metric_cols) == 0:
            logs.append(file_name + ": no metric columns after mapping (skipped) (header=" + str(used_header) + ")")
            continue

        for col in existing_metric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=existing_metric_cols, how="all").copy()
        if df.empty:
            logs.append(file_name + ": empty after metric coercion (skipped)")
            continue

        # ---- Melt ----
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
        logs.append(
            file_name
            + ": loaded "
            + str(len(df_long))
            + " rows; dates "
            + str(df["Date"].min().date())
            + " to "
            + str(df["Date"].max().date())
            + "; header="
            + str(used_header)
        )

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

if not isinstance(data, pd.DataFrame) or data.empty:
    st.error("No data loaded. Check the load log above.")
    st.stop()

st.success("Data loaded: " + str(len(data)) + " rows")
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
    st.warning("No data found for the selected filters.")
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
