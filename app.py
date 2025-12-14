import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import date
from pathlib import Path

# ---------------------------------
# Page config MUST be first
# ---------------------------------
st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.write("✅ App initialized")

# ---------------------------------
# Safe metric sorting
# ---------------------------------
def metric_sort_key(metric_name):
    """
    Robust bureaucratic metric sorter.
    NEVER throws.
    """
    name = str(metric_name)

    letter_match = re.match(r'([A-E])', name)
    letter = letter_match.group(1) if letter_match else "Z"

    number_match = re.search(r'(\d+)', name)
    number = int(number_match.group(1)) if number_match else 0

    sub = 0
    lower = name.lower()
    if 'a.' in lower or ' a ' in lower:
        sub = 1
    elif 'b.' in lower or ' b ' in lower:
        sub = 2

    return (letter, number, sub)

# ---------------------------------
# File list
# ---------------------------------
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

# ---------------------------------
# Cached data loader (FIXED DECORATOR)
# ---------------------------------
@st.cache_data
def load_data(file_paths):
    logs = []
    frames = []

    DATE_FORMATS = [
        None,
        "%Y%m",
        "%Y-%m",
        "%Y-%m-%d",
        "%m/%Y",
        "%m/%d/%Y",
        "%b%y",
        "%b-%y",
    ]

    column_map = {
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

    metric_cols = list(column_map.values())[4:]

    for path in file_paths:
        p = Path(path)
        if not p.exists():
            logs.append(f"⚠️ Missing file: {p.name}")
            continue

        try:
            df = pd.read_csv(p, header=4)
            df.columns = [column_map.get(i, c) for i, c in enumerate(df.columns)]
            df = df[[c for c in column_map.values() if c in df.columns]]

            df = df[df["County_Name"] != "Statewide"]
            df = df.dropna(subset=["County_Name"])
            df["County_Name"] = df["County_Name"].astype(str)

            df["Date"] = pd.NaT

            if "Report_Month" in df:
                rm = df["Report_Month"].astype(str)
                for fmt in DATE_FORMATS:
                    df["Date"] = df["Date"].fillna(
                        pd.to_datetime(rm, format=fmt, errors="coerce")
                    )

            if "Date_Code" in df:
                df["Date"] = df["Date"].fillna(
                    pd.to_datetime(df["Date_Code"], format="%b%y", errors="coerce")
                )

            if df["Date"].notna().sum() == 0:
                logs.append(f"⚠️ Unparsable dates in {p.name}")
                continue

            for c in metric_cols:
                if c in df:
                    df[c] = pd.to_numeric(df[c], errors="coerce")

            df_long = pd.melt(
                df,
                id_vars=["Date", "County_Name"],
                value_vars=[c for c in metric_cols if c in df],
                var_name="Metric",
                value_name="Value",
            )

            frames.append(df_long)
            logs.append(f"✅ Loaded {p.name}")

        except Exception as e:
            logs.append(f"❌ {p.name}: {e}")

    if not frames:
        return pd.DataFrame(), logs

    return pd.concat(frames), logs

# ---------------------------------
# Sidebar upload
# ---------------------------------
st.sidebar.header("Data Source")

uploads = st.sidebar.file_uploader(
    "Upload GR CSVs",
    type="csv",
    accept_multiple_files=True
)

paths = []

if uploads:
    tmp = Path("uploads")
    tmp.mkdir(exist_ok=True)
    for u in uploads:
        p = tmp / u.name
        p.write_bytes(u.getbuffer())
        paths.append(str(p))
else:
    for f in GR_FILE_NAMES:
        if Path(f).exists():
            paths.append(f)
        elif Path("/mnt/data", f).exists():
            paths.append(str(Path("/mnt/data", f)))

# ---------------------------------
# Load & render
# ---------------------------------
data, logs = load_data(tuple(paths))

st.header("🔍 Load Log")
for l in logs:
    st.write(l)

if data.empty:
    st.error("No data loaded.")
    st.stop()

st.success(f"Loaded {len(data):,} rows")

# ---------------------------------
# Filters
# ---------------------------------
counties = sorted(data["County_Name"].unique())
metrics = sorted(data["Metric"].unique(), key=metric_sort_key)

selected_counties = st.sidebar.multiselect(
    "Counties", counties, default=counties[:2]
)

selected_metrics = st.sidebar.multiselect(
    "Metrics", metrics, default=metrics[:1]
)

df = data[
    data["County_Name"].isin(selected_counties)
    & data["Metric"].isin(selected_metrics)
].dropna(subset=["Value"])

# ---------------------------------
# Chart
# ---------------------------------
st.title("GR 237 – General Relief")

chart = alt.Chart(df).mark_line(point=True).encode(
    x="Date:T",
    y=alt.Y("Value:Q", scale=alt.Scale(zero=False)),
    color="County_Name:N",
    tooltip=["County_Name", "Metric", "Value"]
).interactive()

st.altair_chart(chart, use_container_width=True)

st.subheader("📊 Data")
st.dataframe(df)
