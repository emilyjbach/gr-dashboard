import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date

# ----------------------------
# Helper: metric sorting (SAFE, NO LINE WRAPS)
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

    # IMPORTANT: one-line return (no open parentheses)
    return (letter, number, sub)


# ----------------------------
# Files
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
    initial_sidebar_state="expanded",
)

# ----------------------------
# Data prep (NO st.* CALLS INSIDE CACHE)
# ----------------------------
@st.cache_data
def prepare_and_combine_gr_data(file_names):
    all_frames = []

    # Date formats we will try for Report_Month and Date_Code
    # Keeping this as a simple list of strings (no multiline parsing logic that can wrap)
    date_formats = [
        "%Y%m",
        "%Y-%m",
        "%Y-%m-%d",
        "%m/%Y",
        "%m/%d/%Y",
        "%b%y",
        "%b-%y",
        "%b %y",
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

    metric_cols = list(column_index_map.values())[4:]

    county_has_letter = re.compile(r"[A-Za-z]")

    def resolve_path(fname):
        if os.path.exists(fname):
            return fname
        alt_path = os.path.join("/mnt/data", fname)
        if os.path.exists(alt_path):
            return alt_path
        return None

    for fname in file_names:
        path = resolve_path(fname)
        if path is None:
            continue

        try:
            df = pd.read_csv(path, header=4)
        except Exception:
            continue

        try:
            # rename columns by position
            df.columns = [column_index_map.get(i, c) for i, c in enumerate(df.columns)]
            keep = [c for c in column_index_map.values() if c in df.columns]
            df = df[keep].copy()

            # county cleanup
            df = df[df["County_Name"] != "Statewide"].copy()
            df = df.dropna(subset=["County_Name"]).copy()
            df["County_Name"] = df["County_Name"].astype(str).str.strip()
            df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()

            # date parsing
            df["Date"] = pd.NaT

            # parse Report_Month first
            if "Report_Month" in df.columns:
                rm = df["Report_Month"].astype(str).str.strip()

                # numeric YYYYMM attempt
                rm_num = pd.to_numeric(rm, errors="coerce")
                idx = rm_num.dropna().index
                if len(idx) > 0:
                    yyyymm = rm_num.loc[idx].astype(int).astype(str)
                    parsed = pd.to_datetime(yyyymm, format="%Y%m", errors="coerce")
                    df.loc[idx, "Date"] = parsed

                # try remaining formats
                for fmt in date_formats:
                    parsed2 = pd.to_datetime(rm, format=fmt, errors="coerce")
                    df["Date"] = df["Date"].fillna(parsed2)

                # final fallback: pandas auto
                parsed3 = pd.to_datetime(rm, errors="coerce")
                df["Date"] = df["Date"].fillna(parsed3)

            # fallback to Date_Code (older files)
            if "Date_Code" in df.columns:
                dc = df["Date_Code"].astype(str).str.strip()
                dc_up = dc.str.upper()
                # try a few explicit formats, then auto
                parsed_dc1 = pd.to_datetime(dc_up, format="%b%y", errors="coerce")
                df["Date"] = df["Date"].fillna(parsed_dc1)
                parsed_dc2 = pd.to_datetime(dc_up, format="%b-%y", errors="coerce")
                df["Date"] = df["Date"].fillna(parsed_dc2)
                parsed_dc3 = pd.to_datetime(dc_up, format="%b %y", errors="coerce")
                df["Date"] = df["Date"].fillna(parsed_dc3)
                parsed_dc4 = pd.to_datetime(dc, errors="coerce")
                df["Date"] = df["Date"].fillna(parsed_dc4)

            # require some parsed dates
            if df["Date"].notna().sum() == 0:
                continue

            df = df.dropna(subset=["Date"]).copy()

            # numeric metrics
            for col in metric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=metric_cols, how="all").copy()

            # melt to long
            id_vars = ["Date", "County_Name"]
            val_vars = [c for c in metric_cols if c in df.columns]
            df_long = pd.melt(df, id_vars=id_vars, value_vars=val_vars, var_name="Metric", value_name="Value")

            all_frames.append(df_long)

        except Exception:
            continue

    if len(all_frames) == 0:
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)
    combined = combined.sort_values("Date").copy()
    combined = combined.drop_duplicates(subset=["Date", "County_Name", "Metric"], keep="first").copy()
    return combined


# ----------------------------
# Run load + show basic status
# ----------------------------
data = prepare_and_combine_gr_data(GR_FILE_NAMES)

st.header("Data Loading Check")
if not isinstance(data, pd.DataFrame):
    st.error("Data loader did not return a DataFrame.")
    st.stop()

if data.empty:
    st.error("No data loaded. Make sure CSVs are present next to the app or in /mnt/data.")
    st.stop()

min_loaded = data["Date"].min().date()
max_loaded = data["Date"].max().date()
st.success("Loaded rows: " + str(len(data)))
st.write("Loaded date range: " + str(min_loaded) + " to " + str(max_loaded))

# ----------------------------
# Build selectors
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

data_dated = data[(data["Date"].dt.date >= date_range[0]) & (data["Date"].dt.date <= date_range[1])].copy()

selected_counties = st.sidebar.multiselect(
    "Select County(s):",
    options=all_counties,
    default=[c for c in ["Alameda", "Fresno"] if c in all_counties],
)

selected_metrics = st.sidebar.multiselect(
    "Select Metric(s):",
    options=metric_categories,
    default=["B. 6. Total General Relief Cases"] if "B. 6. Total General Relief Cases" in metric_categories else metric_categories[:1],
)

# ----------------------------
# Main
# ----------------------------
st.title("GR 237: General Relief")
st.markdown("Use the sidebar filters to compare multiple counties and multiple metrics on the chart below.")

if (len(selected_counties) == 0) or (len(selected_metrics) == 0):
    st.info("Please select at least one county and one metric from the sidebar.")
    st.stop()

df_filtered = data_dated[data_dated["County_Name"].isin(selected_counties) & data_dated["Metric"].isin(selected_metrics)].copy()
df_filtered = df_filtered.dropna(subset=["Value"]).copy()

if df_filtered.empty:
    st.warning("No data found for the selected filters.")
    st.stop()

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
)

line_chart = base.mark_line(point=True).interactive()
st.altair_chart(line_chart, use_container_width=True)

st.markdown("---")
st.subheader("Underlying Filtered Data")

df_display = df_filtered.drop(columns=["County_Metric"], errors="ignore").copy()
df_display = df_display.rename(columns={"Value": "Value (Cases/Persons/Amount)"})
st.dataframe(df_display)
