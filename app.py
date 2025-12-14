import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date

# Altair silently truncates >5000 rows unless you disable this
alt.data_transformers.disable_max_rows()

st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------
# Metric sorting (safe)
# ----------------------------
def metric_sort_key(metric_name):
    name = str(metric_name)
    m = re.match(r"^\s*([A-E])", name)
    letter = m.group(1) if m else "Z"
    n = re.search(r"(\d+)", name)
    number = int(n.group(1)) if n else 0
    sub = 0
    lower = name.lower()
    if "a." in lower or " a " in lower:
        sub = 1
    elif "b." in lower or " b " in lower:
        sub = 2
    return (letter, number, sub)

# ----------------------------
# Files expected
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

def resolve_path(fname):
    # Streamlit Cloud / this sandbox: uploaded files are in /mnt/data
    p1 = os.path.join("/mnt/data", fname)
    if os.path.exists(p1):
        return p1
    # Fallback: local working dir
    if os.path.exists(fname):
        return fname
    return None

# ----------------------------
# Canonical metric order for GR237
# In these exports, after FFY the remaining columns are numbered 1..N
# We map them by position to these names.
# ----------------------------
METRICS_IN_ORDER = [
    "A. Adjustment",
    "A. 1. Cases brought forward",
    "A. 2. Cases added during month",
    "A. 3. Total cases available",
    "A. 4. Cases discontinued",
    "A. 5. Cases carried forward",

    "B. 6. Total General Relief Cases",
    "B. 6a. Family Cases",
    "B. 6b. One-person Cases",

    "B. 6. Total General Relief Persons",
    "B. 6a. Family Persons",
    "B. 6b. One-person Persons",

    "B. 6. Total GR Expenditure",
    "B. 6(1). Amount in Cash",
    "B. 6(2). Amount in Kind",
    "B. 6a. Family Amount",
    "B. 6b. One-person Amount",

    "C. 7. Cases added during month (IA)",
    "C. 8. Total SSA checks disposed of",
    "C. 8a. Disposed within 1-10 days",
    "C. 9. SSA sent SSI/SSP check directly",
    "C. 10. Denial notice received",

    "D. 11. Reimbursements Cases",
    "D. 11a. SSA check received Cases",
    "D. 11b. Repaid by recipient Cases",
    "D. 11. Reimbursements Amount",
    "D. 11a. SSA check received Amount",
    "D. 11b. Repaid by recipient Amount",

    "E. Net General Relief Expenditure",
]

# ----------------------------
# Robust reader for these "accessible table" CSV exports
# Key fix vs your previous versions:
# - Do NOT assume header=4.
# - These files contain multiline quoted headers.
# - The reliable way is: read a small probe with engine="python", find the row where col0="Date",
#   then read the full file using that row as header.
# ----------------------------
def detect_header_row_by_parsing(path, max_probe_rows=120):
    try:
        probe = pd.read_csv(path, header=None, engine="python", nrows=max_probe_rows)
    except Exception:
        return None

    def norm(x):
        if pd.isna(x):
            return ""
        return str(x).strip().lstrip("\ufeff").strip().lower()

    for i in range(len(probe)):
        c0 = norm(probe.iat[i, 0]) if probe.shape[1] > 0 else ""
        c1 = norm(probe.iat[i, 1]) if probe.shape[1] > 1 else ""
        c2 = norm(probe.iat[i, 2]) if probe.shape[1] > 2 else ""
        c3 = norm(probe.iat[i, 3]) if probe.shape[1] > 3 else ""
        # Typical header row: Date, Month, Year, County Name, County Code, SFY, FFY, 1, 2, 3...
        if c0 == "date" and c1 == "month" and c2 == "year" and "county" in c3:
            return i

    return None

def read_gr_file(path):
    base = os.path.basename(path)
    header_row = detect_header_row_by_parsing(path)

    if header_row is None:
        return None, base + ": could not find header row (Date/Month/Year...) in probe"

    try:
        df = pd.read_csv(path, header=header_row, engine="python")
    except Exception as e:
        return None, base + ": failed reading with detected header row " + str(header_row) + " (" + str(e) + ")"

    # Normalize expected key columns
    rename_map = {
        "Date": "Date_Code",
        "County Name": "County_Name",
        "County name": "County_Name",
        "County": "County_Name",
        "County Code": "County_Code",
        "County code": "County_Code",
    }
    df = df.rename(columns=rename_map)

    return df, base + ": read with header row " + str(header_row)

def parse_date_code(series):
    s = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    # Most files use Jul15 / Aug16 style
    out = pd.to_datetime(s.str.upper(), format="%b%y", errors="coerce")
    # If anything weird sneaks in, let pandas try too
    out = out.fillna(pd.to_datetime(s, errors="coerce"))
    return out

# ----------------------------
# Cached combine
# ----------------------------
@st.cache_data
def load_all(files):
    logs = []
    frames = []

    county_has_letter = re.compile(r"[A-Za-z]")

    for fname in files:
        path = resolve_path(fname)
        if not path:
            logs.append(fname + ": missing file")
            continue

        df, info = read_gr_file(path)
        if df is None or df.empty:
            logs.append(info)
            continue

        # Require these
        if ("County_Name" not in df.columns) or ("Date_Code" not in df.columns):
            logs.append(fname + ": missing County_Name or Date_Code after read")
            continue

        # Clean county
        df["County_Name"] = df["County_Name"].astype(str).str.strip()
        df = df[df["County_Name"] != "Statewide"].copy()
        df = df.dropna(subset=["County_Name"]).copy()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()
        if df.empty:
            logs.append(fname + ": empty after county filtering")
            continue

        # Parse dates
        df["Date"] = parse_date_code(df["Date_Code"])
        df = df.dropna(subset=["Date"]).copy()
        if df.empty:
            logs.append(fname + ": no parsable Date_Code values")
            continue

        # Map metric columns by position after the known “front” columns
        known_front = [c for c in ["Date_Code", "Month", "Year", "County_Name", "County_Code", "SFY", "FFY"] if c in df.columns]
        rest_cols = [c for c in df.columns if c not in known_front]

        # Rename rest columns to canonical metrics by position
        rename_metrics = {}
        for j, c in enumerate(rest_cols):
            if j < len(METRICS_IN_ORDER):
                rename_metrics[c] = METRICS_IN_ORDER[j]
        df = df.rename(columns=rename_metrics)

        metric_cols = [c for c in METRICS_IN_ORDER if c in df.columns]
        if len(metric_cols) == 0:
            logs.append(fname + ": no metric columns recognized after mapping")
            continue

        # Numeric coercion
        for c in metric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=metric_cols, how="all").copy()
        if df.empty:
            logs.append(fname + ": all metric values empty after numeric coercion")
            continue

        # Long
        id_vars = ["Date", "Date_Code", "County_Name"]
        if "County_Code" in df.columns:
            id_vars.append("County_Code")
        if "SFY" in df.columns:
            id_vars.append("SFY")
        if "FFY" in df.columns:
            id_vars.append("FFY")

        df_long = pd.melt(
            df,
            id_vars=id_vars,
            value_vars=metric_cols,
            var_name="Metric",
            value_name="Value",
        )
        df_long = df_long.dropna(subset=["Value"]).copy()

        frames.append(df_long)
        logs.append(
            info
            + "; long_rows="
            + str(len(df_long))
            + "; "
            + str(df["Date"].min().date())
            + " to "
            + str(df["Date"].max().date())
        )

    if not frames:
        return pd.DataFrame(), logs

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("Date").reset_index(drop=True)
    combined = combined.drop_duplicates(subset=["Date", "County_Name", "Metric"], keep="first")
    return combined, logs

# ----------------------------
# UI: preflight
# ----------------------------
st.header("Preflight: CSVs detected in /mnt/data")
try:
    st.write(sorted([f for f in os.listdir("/mnt/data") if f.lower().endswith(".csv")]))
except Exception as e:
    st.write("Could not list /mnt/data: " + str(e))

data, logs = load_all(GR_FILE_NAMES)

st.header("Load Log")
with st.expander("Show load log details", expanded=True):
    for l in logs:
        st.write(l)

if data.empty:
    st.error("No data loaded. The log above tells you exactly what failed.")
    st.stop()

st.success("Loaded " + str(len(data)) + " rows")
st.write("Overall date range: " + str(data["Date"].min().date()) + " to " + str(data["Date"].max().date()))

# ----------------------------
# Filters
# ----------------------------
all_counties = sorted(data["County_Name"].unique().tolist())
metrics = sorted(data["Metric"].unique().tolist(), key=metric_sort_key)

min_date = data["Date"].min().date()
max_date = data["Date"].max().date()

st.sidebar.header("Filter Options")

# default 2017-2019 if possible, else full range
default_start = max(min_date, date(2017, 1, 1))
default_end = min(max_date, date(2019, 12, 31))
if default_end < default_start:
    default_start = min_date
    default_end = max_date

date_range = st.sidebar.slider(
    "Date Range",
    min_value=min_date,
    max_value=max_date,
    value=(default_start, default_end),
    format="YYYY/MM/DD",
)

selected_counties = st.sidebar.multiselect(
    "Counties",
    options=all_counties,
    default=[c for c in ["Alameda", "Fresno"] if c in all_counties] or all_counties[:2],
)

selected_metrics = st.sidebar.multiselect(
    "Metrics",
    options=metrics,
    default=["B. 6. Total General Relief Cases"] if "B. 6. Total General Relief Cases" in metrics else metrics[:1],
)

data_dated = data[
    (data["Date"].dt.date >= date_range[0])
    & (data["Date"].dt.date <= date_range[1])
].copy()

df = data_dated[
    data_dated["County_Name"].isin(selected_counties)
    & data_dated["Metric"].isin(selected_metrics)
].dropna(subset=["Value"]).copy()

# ----------------------------
# Chart
# ----------------------------
st.title("GR 237: General Relief")
st.markdown("Use the sidebar filters to compare multiple counties and multiple metrics on the chart below.")

if df.empty:
    st.warning("No data for the selected filters.")
    st.stop()

df["Series"] = df["County_Name"] + " - " + df["Metric"]

chart = alt.Chart(df).mark_line(point=True).encode(
    x=alt.X("Date:T", axis=alt.Axis(title="Report Month", format="%b %Y")),
    y=alt.Y("Value:Q", scale=alt.Scale(zero=False), title="Value"),
    color=alt.Color("Series:N"),
    tooltip=[
        alt.Tooltip("County_Name:N"),
        alt.Tooltip("Metric:N"),
        alt.Tooltip("Date:T", format="%b %Y"),
        alt.Tooltip("Value:Q", format=",.0f"),
    ],
).interactive()

st.altair_chart(chart, use_container_width=True)

st.markdown("---")
st.subheader("Underlying Data")
st.dataframe(df.drop(columns=["Series"], errors="ignore"))
