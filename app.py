import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date

# ----------------------------
# Streamlit config
# ----------------------------
st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------
# Helper: metric sorting (safe)
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

# ----------------------------
# Robust file resolve
# ----------------------------
def resolve_path(fname):
    # prioritize /mnt/data since you uploaded there
    p1 = os.path.join("/mnt/data", fname)
    if os.path.exists(p1):
        return p1
    # fallback to local working dir
    if os.path.exists(fname):
        return fname
    return None

# ----------------------------
# Cached loader: returns (df, logs)
# No st.* calls inside cache.
# ----------------------------
@st.cache_data
def prepare_and_combine_gr_data(file_names):
    logs = []
    frames = []

    # Column mapping for the common header=4 layout
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

    # Try a few common header offsets; different fiscal years shift sometimes
    header_candidates = [4, 5, 3, 2, 1, 0]

    def try_read_csv(path):
        last_err = None
        for h in header_candidates:
            try:
                df0 = pd.read_csv(path, header=h)
                if isinstance(df0, pd.DataFrame) and df0.shape[1] >= 6 and df0.shape[0] >= 1:
                    return df0, h, None
            except Exception as e:
                last_err = str(e)
        return None, None, last_err

    def parse_dates_from_series(series):
        s = series.astype(str).str.strip()
        s = s.str.replace(r"\.0$", "", regex=True)

        out = pd.Series(pd.NaT, index=s.index)

        # 1) pandas free parse first (handles 7/17, 07-17, July 2017, etc.)
        out = out.fillna(pd.to_datetime(s, errors="coerce"))

        # 2) numeric YYYYMM pass
        num = pd.to_numeric(s, errors="coerce")
        idx = num.dropna().index
        if len(idx) > 0:
            yyyymm = num.loc[idx].astype(int).astype(str)
            out.loc[idx] = out.loc[idx].fillna(pd.to_datetime(yyyymm, format="%Y%m", errors="coerce"))

        # 3) a few strict fills (for stubborn strings)
        strict_formats = ["%b%y", "%b-%y", "%b %y", "%b %Y", "%B %Y", "%Y-%m", "%m/%Y", "%m/%y", "%m-%y"]
        for fmt in strict_formats:
            out = out.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))

        return out

    for fname in file_names:
        path = resolve_path(fname)
        if not path:
            logs.append(fname + ": missing (not found in /mnt/data or working dir)")
            continue

        df_raw, used_header, read_err = try_read_csv(path)
        if df_raw is None:
            logs.append(fname + ": could not read (" + str(read_err) + ")")
            continue

        # Rename columns by position
        df = df_raw.copy()
        df.columns = [column_index_map.get(i, col) for i, col in enumerate(df.columns)]

        # Keep mapped columns that exist
        keep_cols = [c for c in column_index_map.values() if c in df.columns]
        df = df[keep_cols].copy()

        if "County_Name" not in df.columns:
            logs.append(fname + ": County_Name missing after mapping (header=" + str(used_header) + ")")
            continue

        df = df[df["County_Name"] != "Statewide"].copy()
        df = df.dropna(subset=["County_Name"]).copy()
        df["County_Name"] = df["County_Name"].astype(str).str.strip()

        numeric_mask = df["County_Name"].str.match(r"^\d+(\.\d+)?$")
        df = df[~numeric_mask].copy()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()

        df["Date"] = pd.NaT

        # Try both mapped columns if present
        candidates = []
        if "Date_Code" in df.columns:
            candidates.append(df["Date_Code"])
        if "Report_Month" in df.columns:
            candidates.append(df["Report_Month"])

        for ser in candidates:
            if df["Date"].notna().sum() > 0:
                break
            df["Date"] = df["Date"].fillna(parse_dates_from_series(ser))

        if df["Date"].notna().sum() == 0:
            logs.append(fname + ": no parsable dates (header=" + str(used_header) + ")")
            continue

        df = df.dropna(subset=["Date"]).copy()

        # Metrics: ONLY those that exist in this file
        existing_metric_cols = [c for c in metric_cols_full if c in df.columns]
        if len(existing_metric_cols) == 0:
            logs.append(fname + ": no metric columns after mapping (header=" + str(used_header) + ")")
            continue

        for col in existing_metric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=existing_metric_cols, how="all").copy()
        if df.empty:
            logs.append(fname + ": all metrics empty after coercion")
            continue

        df_long = pd.melt(
            df,
            id_vars=["Date", "County_Name"],
            value_vars=existing_metric_cols,
            var_name="Metric",
            value_name="Value",
        )

        frames.append(df_long)
        logs.append(
            fname
            + ": loaded "
            + str(len(df_long))
            + " rows; "
            + str(df["Date"].min().date())
            + " to "
            + str(df["Date"].max().date())
            + "; header="
            + str(used_header)
        )

    if len(frames) == 0:
        return pd.DataFrame(), logs

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("Date").reset_index(drop=True)
    combined = combined.drop_duplicates(subset=["Date", "County_Name", "Metric"], keep="first")
    return combined, logs

# ----------------------------
# MAIN: show what files exist before loading
# ----------------------------
st.header("Preflight: Files detected in /mnt/data")
try:
    md_files = sorted([f for f in os.listdir("/mnt/data") if f.lower().endswith(".csv")])
    st.write(md_files)
except Exception as e:
    st.write("Could not list /mnt/data: " + str(e))

st.header("Load Log")
data, logs = prepare_and_combine_gr_data(GR_FILE_NAMES)

with st.expander("Show load log details", expanded=True):
    for l in logs:
        st.write(l)

if data.empty:
    st.error("No data loaded. The log above will show exactly which file(s) failed and why.")
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
date_range = st.sidebar.slider(
    "Date Range (defaults to 2017-2019 if available)",
    min_value=min_date,
    max_value=max_date,
    value=(
        max(min_date, date(2017, 1, 1)),
        min(max_date, date(2019, 12, 31)) if max_date >= date(2019, 12, 31) else max_date,
    ),
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
    (data["Date"].dt.date >= date_range[0]) & (data["Date"].dt.date <= date_range[1])
].copy()

df = data_dated[
    data_dated["County_Name"].isin(selected_counties) & data_dated["Metric"].isin(selected_metrics)
].dropna(subset=["Value"])

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
