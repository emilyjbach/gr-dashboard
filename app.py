import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import date
from pathlib import Path

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
def metric_sort_key(metric_name: str):
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
# Files expected (repo-relative)
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
# Canonical GR237 metric order
# (maps numbered columns 1..N by position after the first fixed fields)
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
# File resolution (GitHub/Streamlit-friendly)
# Looks in:
# - same folder as app.py
# - optional ./data subfolder
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
CANDIDATE_DIRS = [BASE_DIR, BASE_DIR / "data"]

def resolve_path(fname: str) -> Path | None:
    for d in CANDIDATE_DIRS:
        p = d / fname
        if p.exists():
            return p
    return None

# ----------------------------
# Robust header detection for multiline "accessible table" CSV exports
# We parse a probe chunk with engine="python" and locate a row whose first columns
# look like Date, Month, Year, County...
# ----------------------------
def detect_header_row(path: Path, max_probe_rows: int = 200) -> int | None:
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

        # Typical header row:
        # Date, Month, Year, County Name, County Code, SFY, FFY, 1, 2, 3...
        if c0 == "date" and c1 == "month" and c2 == "year" and ("county" in c3):
            return i

        # Some variants: County may be in col4 if an extra blank col exists; loosen slightly
        if c0 == "date" and c1 == "month" and c2 == "year" and ("county" in (c3 or "")):
            return i

    return None

def read_gr_file(path: Path):
    header_row = detect_header_row(path)
    if header_row is None:
        return None, f"{path.name}: could not find header row"

    try:
        df = pd.read_csv(path, header=header_row, engine="python")
    except Exception as e:
        return None, f"{path.name}: failed read at header={header_row} ({e})"

    # Normalize key columns
    rename_map = {
        "Date": "Date_Code",
        "County Name": "County_Name",
        "County name": "County_Name",
        "County": "County_Name",
        "County Code": "County_Code",
        "County code": "County_Code",
        "Report Month": "Report_Month",
        "Report_Month": "Report_Month",
    }
    df = df.rename(columns=rename_map)

    return df, f"{path.name}: header row {header_row}"

# ----------------------------
# Date parsing (handles old + new)
# ----------------------------
def parse_date_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)

    out = pd.Series(pd.NaT, index=s.index)

    # Jul15 / Aug21 style
    out = out.fillna(pd.to_datetime(s.str.upper(), format="%b%y", errors="coerce"))

    # Numeric YYYYMM
    num = pd.to_numeric(s, errors="coerce")
    idx = num.dropna().index
    if len(idx) > 0:
        yyyymm = num.loc[idx].astype(int).astype(str)
        out.loc[idx] = out.loc[idx].fillna(pd.to_datetime(yyyymm, format="%Y%m", errors="coerce"))

    # Common string formats
    for fmt in ("%Y-%m", "%Y-%m-%d", "%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
        out = out.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))

    # Final auto
    out = out.fillna(pd.to_datetime(s, errors="coerce"))
    return out

def build_date(df: pd.DataFrame) -> pd.Series:
    # 1) Prefer Date_Code if present
    if "Date_Code" in df.columns:
        d = parse_date_series(df["Date_Code"])
        if d.notna().any():
            return d

    # 2) Then Report_Month if present
    if "Report_Month" in df.columns:
        d = parse_date_series(df["Report_Month"])
        if d.notna().any():
            return d

    # 3) Then Month + Year columns
    if "Month" in df.columns and "Year" in df.columns:
        month = pd.to_numeric(df["Month"], errors="coerce")
        year = pd.to_numeric(df["Year"], errors="coerce")
        ok = month.notna() & year.notna()
        d = pd.Series(pd.NaT, index=df.index)
        if ok.any():
            mm = month[ok].astype(int).astype(str).str.zfill(2)
            yy = year[ok].astype(int).astype(str)
            d.loc[ok] = pd.to_datetime(yy + "-" + mm + "-01", errors="coerce")
        if d.notna().any():
            return d

    return pd.Series(pd.NaT, index=df.index)

# ----------------------------
# Cached load/combine
# ----------------------------
@st.cache_data
def load_all(files):
    logs = []
    frames = []

    county_has_letter = re.compile(r"[A-Za-z]")

    for fname in files:
        path = resolve_path(fname)
        if path is None:
            logs.append(f"{fname}: missing (not found next to app.py or in ./data)")
            continue

        df, info = read_gr_file(path)
        if df is None or df.empty:
            logs.append(info)
            continue

        # Must have County_Name
        if "County_Name" not in df.columns:
            logs.append(f"{fname}: missing County_Name after read")
            continue

        # Clean county (keep “alphanumeric” in the sense: must contain at least one letter)
        df["County_Name"] = df["County_Name"].astype(str).str.strip()
        df = df[df["County_Name"] != "Statewide"].copy()
        df = df.dropna(subset=["County_Name"]).copy()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()
        if df.empty:
            logs.append(f"{fname}: empty after county filtering")
            continue

        # Dates
        df["Date"] = build_date(df)
        df = df.dropna(subset=["Date"]).copy()
        if df.empty:
            logs.append(f"{fname}: no parsable dates")
            continue

        # Metric mapping by position after fixed front fields
        known_front = [c for c in ["Date_Code", "Month", "Year", "County_Name", "County_Code", "SFY", "FFY", "Report_Month"] if c in df.columns]
        rest_cols = [c for c in df.columns if c not in known_front]

        # Rename remaining columns into canonical metrics by position (safe even if headers are 1..N)
        rename_metrics = {}
        for j, c in enumerate(rest_cols):
            if j < len(METRICS_IN_ORDER):
                rename_metrics[c] = METRICS_IN_ORDER[j]
        df = df.rename(columns=rename_metrics)

        metric_cols = [c for c in METRICS_IN_ORDER if c in df.columns]
        if len(metric_cols) == 0:
            logs.append(f"{fname}: no metric columns recognized after mapping")
            continue

        for c in metric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=metric_cols, how="all").copy()
        if df.empty:
            logs.append(f"{fname}: all metric values empty after numeric coercion")
            continue

        # Long
        id_vars = ["Date", "County_Name"]
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
        ).dropna(subset=["Value"]).copy()

        frames.append(df_long)
        logs.append(
            info
            + " | long_rows="
            + str(len(df_long))
            + " | "
            + str(df["Date"].min().date())
            + " → "
            + str(df["Date"].max().date())
        )

    if not frames:
        return pd.DataFrame(), logs

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("Date").reset_index(drop=True)
    combined = combined.drop_duplicates(subset=["Date", "County_Name", "Metric"], keep="first")
    return combined, logs

# ----------------------------
# App header (make the top not weird)
# ----------------------------
st.title("GR 237: General Relief")
st.caption("Filter counties, metrics, and date range in the sidebar. Data should display through 2025 if the FY files are present (20–21 through 24–25).")

with st.sidebar:
    st.header("Filter Options")
    show_debug = st.checkbox("Show debug log", value=False)

# Load data
data, logs = load_all(GR_FILE_NAMES)

if data.empty:
    st.error("No data loaded. Turn on “Show debug log” in the sidebar to see exactly what failed.")
    if show_debug:
        st.subheader("Debug log")
        for l in logs:
            st.write(l)
    st.stop()

# Quick range display
min_date = data["Date"].min().date()
max_date = data["Date"].max().date()
st.write(f"**Loaded:** {len(data):,} rows • **Date range:** {min_date} → {max_date}")

# Sidebar filters (ensure end defaults to max_date so you see through 2025)
with st.sidebar:
    all_counties = sorted(data["County_Name"].unique().tolist())
    metrics = sorted(data["Metric"].unique().tolist(), key=metric_sort_key)

    # Default: start 2017 if available, end = max (shows through 2025)
    default_start = max(min_date, date(2017, 1, 1))
    default_end = max_date

    date_range = st.slider(
        "Date Range",
        min_value=min_date,
        max_value=max_date,
        value=(default_start, default_end),
        format="YYYY/MM/DD",
    )

    selected_counties = st.multiselect(
        "Counties",
        options=all_counties,
        default=[c for c in ["Alameda", "Fresno"] if c in all_counties] or all_counties[:2],
    )

    selected_metrics = st.multiselect(
        "Metrics",
        options=metrics,
        default=["B. 6. Total General Relief Cases"] if "B. 6. Total General Relief Cases" in metrics else metrics[:1],
    )

    if show_debug:
        st.markdown("---")
        st.subheader("Debug log")
        for l in logs:
            st.write(l)

# Filter data
data_dated = data[
    (data["Date"].dt.date >= date_range[0]) &
    (data["Date"].dt.date <= date_range[1])
].copy()

df = data_dated[
    data_dated["County_Name"].isin(selected_counties) &
    data_dated["Metric"].isin(selected_metrics)
].dropna(subset=["Value"]).copy()

if df.empty:
    st.warning("No data for the selected filters.")
    st.stop()

df["Series"] = df["County_Name"] + " - " + df["Metric"]

# Chart
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
