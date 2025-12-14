import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date

# Prevent Altair from silently truncating datasets > 5000 rows
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
    p = os.path.join("/mnt/data", fname)
    if os.path.exists(p):
        return p
    if os.path.exists(fname):
        return fname
    return None

# Canonical GR237 metric order (maps numeric columns 1..N -> names by position)
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
# Robust header detection
# ----------------------------
def find_real_header_row(path, max_lines=250):
    """
    Finds the line index (0-based) where the actual CSV header begins.
    We look for a line containing Date,Month,Year (case-insensitive),
    handling BOM and leading whitespace.
    """
    try:
        with open(path, "r", errors="ignore") as f:
            for i in range(max_lines):
                line = f.readline()
                if not line:
                    break
                s = line.strip()
                s = s.lstrip("\ufeff").strip()
                low = s.lower()
                # robust contains check (not startswith)
                if ("date,month,year" in low) and ("county" in low):
                    return i
    except Exception:
        return None
    return None

def find_data_start_row(path, max_lines=250):
    """
    Fallback: first row that looks like Jul15,... (3-letter month + 2-digit year)
    """
    try:
        with open(path, "r", errors="ignore") as f:
            for i in range(max_lines):
                line = f.readline()
                if not line:
                    break
                s = line.strip().lstrip("\ufeff").strip()
                if re.match(r"^[A-Za-z]{3}\d{2},", s):
                    return i
    except Exception:
        return None
    return None

def read_gr_file(path):
    """
    Reads a GR file by locating the true header row.
    Returns (df, info_string).
    """
    base = os.path.basename(path)

    header_row = find_real_header_row(path)
    if header_row is not None:
        df = pd.read_csv(path, header=header_row)
        info = base + ": read using header row " + str(header_row)
    else:
        # fallback: headerless, start at first data row
        data_start = find_data_start_row(path)
        if data_start is None:
            return None, base + ": could not detect header row or data start"
        df = pd.read_csv(path, header=None, skiprows=data_start)
        info = base + ": read as headerless starting row " + str(data_start)

        # assign canonical first fields then map metrics by position
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
                if 0 <= pos < len(METRICS_IN_ORDER):
                    colnames.append(METRICS_IN_ORDER[pos])
                else:
                    colnames.append("X" + str(k))
        df.columns = colnames
        return df, info

    # Normalize expected key columns for header-mode files
    rename_map = {
        "Date": "Date_Code",
        "County": "County_Name",
        "County Name": "County_Name",
        "County name": "County_Name",
        "County_Name": "County_Name",
        "County Code": "County_Code",
        "County code": "County_Code",
        "County_Code": "County_Code",
        "Month": "Month",
        "Year": "Year",
        "SFY": "SFY",
        "FFY": "FFY",
    }
    df = df.rename(columns=rename_map)

    # If metrics are numbered (1,2,3...) rename them by position after the first known fields
    known_fields = [c for c in ["Date_Code", "Month", "Year", "County_Name", "County_Code", "SFY", "FFY"] if c in df.columns]
    rest_cols = [c for c in df.columns if c not in known_fields]

    # Many files have metric columns literally named 1..29 (as ints or strings). We map by position regardless.
    new_names = {}
    for j, c in enumerate(rest_cols):
        if j < len(METRICS_IN_ORDER):
            new_names[c] = METRICS_IN_ORDER[j]
    df = df.rename(columns=new_names)

    return df, info

# ----------------------------
# Date parsing
# ----------------------------
def parse_date_code(series):
    """
    GR files use Date_Code like Jul15, Aug17, etc.
    Parse with %b%y; fall back to pandas for any oddities.
    """
    s = series.astype(str).str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)
    out = pd.to_datetime(s.str.upper(), format="%b%y", errors="coerce")
    out = out.fillna(pd.to_datetime(s, errors="coerce"))
    return out

# ----------------------------
# Load all (cached)
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

        # Must have these after read
        if ("County_Name" not in df.columns) or ("Date_Code" not in df.columns):
            logs.append(fname + ": missing County_Name or Date_Code after read")
            continue

        # County cleanup
        df["County_Name"] = df["County_Name"].astype(str).str.strip()
        df = df[df["County_Name"] != "Statewide"].copy()
        df = df.dropna(subset=["County_Name"]).copy()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()
        if df.empty:
            logs.append(fname + ": empty after county filtering")
            continue

        # Date parse
        df["Date"] = parse_date_code(df["Date_Code"])
        df = df.dropna(subset=["Date"]).copy()
        if df.empty:
            logs.append(fname + ": no parsable Date_Code values")
            continue

        # Metric columns present in this file
        metric_cols = [c for c in METRICS_IN_ORDER if c in df.columns]
        if len(metric_cols) == 0:
            logs.append(fname + ": no metric columns recognized")
            continue

        # Numeric coercion
        for c in metric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=metric_cols, how="all").copy()
        if df.empty:
            logs.append(fname + ": all metric values empty after coercion")
            continue

        # Long format
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
    st.error("No data loaded. The log above tells you which file failed and why.")
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
