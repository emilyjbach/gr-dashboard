import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date

# IMPORTANT: prevent Altair from silently truncating >5000 rows
alt.data_transformers.disable_max_rows()

st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------
# Metric sorting
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
# Files expected in /mnt/data
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
    p1 = os.path.join("/mnt/data", fname)
    if os.path.exists(p1):
        return p1
    if os.path.exists(fname):
        return fname
    return None

# ----------------------------
# Canonical metric order
# (GR 237 layout: metrics start after first 7 fields)
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

MONTHCODE_RE = re.compile(r"^[A-Za-z]{3}\d{2}$")  # Jul15

def parse_monthcode_series(s):
    s = s.astype(str).str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)
    # Try Jul15 style first; then let pandas handle anything else (e.g., July 2015)
    out = pd.to_datetime(s.str.upper(), format="%b%y", errors="coerce")
    out = out.fillna(pd.to_datetime(s, errors="coerce"))
    return out

def find_header_or_data_start(path):
    """
    Detect whether file has an explicit header row like:
    Date,Month,Year,County,County Code,SFY,FFY,...
    OR whether it starts with data rows like:
    Jul15,7,2015,Alameda,...
    """
    try:
        with open(path, "r", errors="ignore") as f:
            for i in range(0, 120):
                line = f.readline()
                if not line:
                    break
                s = line.strip()
                low = s.lower()
                if low.startswith("date,month,year,county"):
                    return ("header", i)
                if re.match(r"^[A-Za-z]{3}\d{2},", s):
                    return ("data", i)
    except Exception:
        pass
    return (None, None)

def read_gr_file(path):
    mode, idx = find_header_or_data_start(path)
    base = os.path.basename(path)

    if mode == "header":
        df = pd.read_csv(path, header=idx)

        # Normalize column names that commonly appear
        rename_map = {
            "Date": "Date_Code",
            "County": "County_Name",
            "County Name": "County_Name",
            "County name": "County_Name",
            "County Code": "County_Code",
            "County code": "County_Code",
            "Month": "Month",
            "Year": "Year",
            "SFY": "SFY",
            "FFY": "FFY",
        }
        df = df.rename(columns=rename_map)

        known = [c for c in ["Date_Code", "Month", "Year", "County_Name", "County_Code", "SFY", "FFY"] if c in df.columns]
        rest = [c for c in df.columns if c not in known]

        # Rename remaining columns by position into METRICS_IN_ORDER
        new_names = {}
        for j, c in enumerate(rest):
            if j < len(METRICS_IN_ORDER):
                new_names[c] = METRICS_IN_ORDER[j]
        df = df.rename(columns=new_names)

        return df, base + ": header row " + str(idx)

    if mode == "data":
        df = pd.read_csv(path, header=None, skiprows=idx)
        ncols = df.shape[1]

        colnames = []
        for k in range(ncols):
            if k == 0:
                colnames.append("Date_Code")
            elif k == 1:
                colnames.append("Month")
            elif k == 2:
                colnames.append("Year")
            elif k == 3:
                colnames.append("County_Name")
            elif k == 4:
                colnames.append("County_Code")
            elif k == 5:
                colnames.append("SFY")
            elif k == 6:
                colnames.append("FFY")
            else:
                pos = k - 7
                if pos < len(METRICS_IN_ORDER):
                    colnames.append(METRICS_IN_ORDER[pos])
                else:
                    colnames.append("X" + str(k))

        df.columns = colnames
        return df, base + ": data start " + str(idx)

    return None, base + ": could not detect header/data start"

# ----------------------------
# Cached load/combine
# ----------------------------
@st.cache_data
def load_all(files):
    logs = []
    frames_long = []
    county_has_letter = re.compile(r"[A-Za-z]")

    for fname in files:
        path = resolve_path(fname)
        if not path:
            logs.append(fname + ": missing")
            continue

        df, info = read_gr_file(path)
        if df is None or df.empty:
            logs.append(info)
            continue

        if "County_Name" not in df.columns or "Date_Code" not in df.columns:
            logs.append(os.path.basename(path) + ": missing County_Name or Date_Code after read")
            continue

        df["County_Name"] = df["County_Name"].astype(str).str.strip()
        df = df[df["County_Name"] != "Statewide"].copy()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()
        if df.empty:
            logs.append(os.path.basename(path) + ": empty after county filtering")
            continue

        df["Date"] = parse_monthcode_series(df["Date_Code"])
        df = df.dropna(subset=["Date"]).copy()
        if df.empty:
            logs.append(os.path.basename(path) + ": no parsable Date_Code values")
            continue

        metric_cols = [c for c in METRICS_IN_ORDER if c in df.columns]
        if len(metric_cols) == 0:
            logs.append(os.path.basename(path) + ": no metric columns recognized")
            continue

        for c in metric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=metric_cols, how="all").copy()
        if df.empty:
            logs.append(os.path.basename(path) + ": all metrics empty after coercion")
            continue

        keep_id = ["Date", "Date_Code", "County_Name"]
        if "County_Code" in df.columns:
            keep_id.append("County_Code")
        if "SFY" in df.columns:
            keep_id.append("SFY")
        if "FFY" in df.columns:
            keep_id.append("FFY")

        df_long = pd.melt(
            df,
            id_vars=keep_id,
            value_vars=metric_cols,
            var_name="Metric",
            value_name="Value",
        )

        df_long = df_long.dropna(subset=["Value"]).copy()
        frames_long.append(df_long)

        logs.append(info + "; long_rows=" + str(len(df_long)) + "; " + str(df["Date"].min().date()) + " to " + str(df["Date"].max().date()))

    if len(frames_long) == 0:
        return pd.DataFrame(), logs

    combined = pd.concat(frames_long, ignore_index=True)
    combined = combined.sort_values("Date").reset_index(drop=True)
    combined = combined.drop_duplicates(subset=["Date", "County_Name", "Metric"], keep="first")
    return combined, logs

# ----------------------------
# UI: Preflight + load
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
    st.error("No data loaded. See log above.")
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

# default to 2017-2019 window if available
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
    (data["Date"].dt.date >= date_range[0]) &
    (data["Date"].dt.date <= date_range[1])
].copy()

df = data_dated[
    data_dated["County_Name"].isin(selected_counties) &
    data_dated["Metric"].isin(selected_metrics)
].dropna(subset=["Value"]).copy()

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
