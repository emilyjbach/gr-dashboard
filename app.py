import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date

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

st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------
# Data loader
# ----------------------------
@st.cache_data
def prepare_and_combine_gr_data(file_names):
    frames = []
    logs = []

    DATE_FORMATS = [
        "%Y%m",
        "%Y-%m",
        "%Y-%m-%d",
        "%m/%Y",
        "%m/%d/%Y",
        "%b%y",
        "%b-%y",
        "%b %y",
        "%b %Y",   # <<< FIX FOR 16-17
        "%B %Y",   # <<< FIX FOR 16-17
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
        35: "E. Net General Relief Expenditure",
    }

    metric_cols = list(column_index_map.values())[4:]
    county_has_letter = re.compile(r"[A-Za-z]")

    def resolve_path(fname):
        p = os.path.join("/mnt/data", fname)
        return p if os.path.exists(p) else None

    for fname in file_names:
        path = resolve_path(fname)
        if not path:
            logs.append(fname + ": missing")
            continue

        df = pd.read_csv(path, header=4)
        df.columns = [column_index_map.get(i, c) for i, c in enumerate(df.columns)]
        df = df[[c for c in column_index_map.values() if c in df.columns]]

        df = df[df["County_Name"] != "Statewide"]
        df = df.dropna(subset=["County_Name"])
        df["County_Name"] = df["County_Name"].astype(str).str.strip()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))]

        df["Date"] = pd.NaT

        for source in ["Date_Code", "Report_Month"]:
            if source in df.columns:
                s = df[source].astype(str).str.strip()
                for fmt in DATE_FORMATS:
                    parsed = pd.to_datetime(s, format=fmt, errors="coerce")
                    df["Date"] = df["Date"].fillna(parsed)
                df["Date"] = df["Date"].fillna(pd.to_datetime(s, errors="coerce"))

        if df["Date"].notna().sum() == 0:
            logs.append(fname + ": no parsable dates")
            continue

        for col in metric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=metric_cols, how="all")

        df_long = pd.melt(
            df,
            id_vars=["Date", "County_Name"],
            value_vars=[c for c in metric_cols if c in df.columns],
            var_name="Metric",
            value_name="Value",
        )

        frames.append(df_long)
        logs.append(
            fname
            + ": loaded "
            + str(len(df_long))
            + " rows ("
            + str(df["Date"].min().date())
            + " to "
            + str(df["Date"].max().date())
            + ")"
        )

    if not frames:
        return pd.DataFrame(), logs

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("Date")
    combined = combined.drop_duplicates(["Date", "County_Name", "Metric"])
    return combined, logs

# ----------------------------
# Run load
# ----------------------------
data, logs = prepare_and_combine_gr_data(GR_FILE_NAMES)

st.header("Data Loading Check")
with st.expander("Load log"):
    for l in logs:
        st.write(l)

if data.empty:
    st.error("No data loaded.")
    st.stop()

st.success(
    "Loaded "
    + str(len(data))
    + " rows | "
    + str(data["Date"].min().date())
    + " → "
    + str(data["Date"].max().date())
)

# ----------------------------
# Filters
# ----------------------------
all_counties = sorted(data["County_Name"].unique())
metrics = sorted(data["Metric"].unique(), key=metric_sort_key)

min_date = data["Date"].min().date()
max_date = data["Date"].max().date()

date_range = st.sidebar.slider(
    "Date Range",
    min_date,
    max_date,
    (max(min_date, date(2017, 1, 1)), max_date),
)

selected_counties = st.sidebar.multiselect(
    "Counties", all_counties, default=[c for c in ["Alameda", "Fresno"] if c in all_counties]
)

selected_metrics = st.sidebar.multiselect(
    "Metrics",
    metrics,
    default=["B. 6. Total General Relief Cases"] if "B. 6. Total General Relief Cases" in metrics else metrics[:1],
)

df = data[
    (data["County_Name"].isin(selected_counties))
    & (data["Metric"].isin(selected_metrics))
    & (data["Date"].dt.date >= date_range[0])
    & (data["Date"].dt.date <= date_range[1])
].dropna(subset=["Value"])

# ----------------------------
# Chart
# ----------------------------
st.title("GR 237: General Relief")

df["Series"] = df["County_Name"] + " - " + df["Metric"]

chart = alt.Chart(df).mark_line(point=True).encode(
    x=alt.X("Date:T", title="Report Month", format="%b %Y"),
    y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
    color="Series:N",
    tooltip=["County_Name", "Metric", alt.Tooltip("Value:Q", format=",.0f")],
).interactive()

st.altair_chart(chart, use_container_width=True)

st.subheader("Underlying Data")
st.dataframe(df.drop(columns=["Series"], errors="ignore"))
