import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import date
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# Altair silently truncates datasets > 5000 rows unless disabled
alt.data_transformers.disable_max_rows()

st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Always render something at the top so failures don't look like a blank page
st.title("GR 237: General Relief")
st.caption("Use the sidebar filters. Enable debug to see exactly what each CSV did during loading.")

with st.sidebar:
    st.header("Filter Options")
    show_debug = st.checkbox("Show debug log", value=False)

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
# Files (repo-relative)
# Put CSVs next to app.py OR in ./data/
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
# Canonical metric order for GR237
# (maps numbered columns 1..N)
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
# Path resolution (GitHub/Streamlit Cloud-friendly)
# ----------------------------
def get_base_dir():
    try:
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()

BASE_DIR = get_base_dir()
CANDIDATE_DIRS = [BASE_DIR, BASE_DIR / "data"]

def resolve_path(fname):
    for d in CANDIDATE_DIRS:
        p = d / fname
        if p.exists():
            return p
    return None

# ----------------------------
# Header detection
# Brute-force header rows 0..80, score column tokens
# ----------------------------
def _norm(x):
    if x is None:
        return ""
    return str(x).strip().lstrip("\ufeff").strip().lower()

def score_columns(cols):
    ncols = [_norm(c) for c in cols]
    joined = " ".join(ncols)

    score = 0
    if "county" in joined:
        score += 5
    if ("date" in joined) or ("report month" in joined) or ("report_month" in joined):
        score += 4
    if "month" in joined:
        score += 2
    if "year" in joined:
        score += 2
    if "sfy" in joined:
        score += 1
    if "ffy" in joined:
        score += 1

    # bonus if we see many numeric-ish headers like 1,2,3...
    numlike = 0
    for c in ncols:
        if re.fullmatch(r"\d+", c):
            numlike += 1
    if numlike >= 5:
        score += 2

    return score

def find_best_header_row(path, max_h=80):
    best_h = None
    best_score = -1
    for h in range(0, max_h + 1):
        try:
            df1 = pd.read_csv(path, header=h, engine="python", nrows=1)
            s = score_columns(df1.columns)
            if s > best_score:
                best_score = s
                best_h = h
        except Exception:
            continue
    if best_h is None or best_score < 7:
        return None
    return best_h

def normalize_columns(df):
    rename_map = {}
    for c in df.columns:
        low = _norm(c)
        if low in ("date", "date_code", "date code"):
            rename_map[c] = "Date_Code"
        elif low in ("report month", "report_month", "reportmonth"):
            rename_map[c] = "Report_Month"
        elif low in ("county", "county name", "county_name", "countyname"):
            rename_map[c] = "County_Name"
        elif low in ("county code", "county_code", "countycode"):
            rename_map[c] = "County_Code"
        elif low == "month":
            rename_map[c] = "Month"
        elif low == "year":
            rename_map[c] = "Year"
        elif low == "sfy":
            rename_map[c] = "SFY"
        elif low == "ffy":
            rename_map[c] = "FFY"

    df = df.rename(columns=rename_map)

    # Soft matches if still missing
    if "County_Name" not in df.columns:
        for c in df.columns:
            lc = _norm(c)
            if "county" in lc and "name" in lc:
                df = df.rename(columns={c: "County_Name"})
                break
        if "County_Name" not in df.columns:
            for c in df.columns:
                if _norm(c) == "county":
                    df = df.rename(columns={c: "County_Name"})
                    break

    if "Date_Code" not in df.columns and "Report_Month" not in df.columns:
        for c in df.columns:
            lc = _norm(c)
            if "report" in lc and "month" in lc:
                df = df.rename(columns={c: "Report_Month"})
                break
            if lc in ("date", "date_code", "date code"):
                df = df.rename(columns={c: "Date_Code"})
                break

    return df

def read_gr_file(path):
    h = find_best_header_row(path)
    if h is None:
        return None, f"{path.name}: could not find a plausible header row (scan 0–80)"

    try:
        df = pd.read_csv(path, header=h, engine="python")
    except Exception as e:
        return None, f"{path.name}: failed read at header={h} ({e})"

    df = normalize_columns(df)
    return df, f"{path.name}: header={h}"

# ----------------------------
# Date parsing (old + new)
# ----------------------------
def parse_date_series(s):
    s = s.astype(str).str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)

    out = pd.Series(pd.NaT, index=s.index)

    # Jul15 / Aug21 style
    out = out.fillna(pd.to_datetime(s.str.upper(), format="%b%y", errors="coerce"))

    # Numeric YYYYMM (202007)
    num = pd.to_numeric(s, errors="coerce")
    idx = num.dropna().index
    if len(idx) > 0:
        yyyymm = num.loc[idx].astype(int).astype(str)
        out.loc[idx] = out.loc[idx].fillna(pd.to_datetime(yyyymm, format="%Y%m", errors="coerce"))

    # Common newer formats
    for fmt in ("%Y-%m", "%Y-%m-%d", "%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
        out = out.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))

    # Final auto
    out = out.fillna(pd.to_datetime(s, errors="coerce"))
    return out

def build_date(df):
    if "Date_Code" in df.columns:
        d = parse_date_series(df["Date_Code"])
        if d.notna().any():
            return d
    if "Report_Month" in df.columns:
        d = parse_date_series(df["Report_Month"])
        if d.notna().any():
            return d
    if "Month" in df.columns and "Year" in df.columns:
        month = pd.to_numeric(df["Month"], errors="coerce")
        year = pd.to_numeric(df["Year"], errors="coerce")
        ok = month.notna() & year.notna()
        d = pd.Series(pd.NaT, index=df.index)
        if ok.any():
            mm = month[ok].astype(int).astype(str).str.zfill(2)
            yy = year[ok].astype(int).astype(str)
            d.loc[ok] = pd.to_datetime(yy + "-" + mm + "-01", errors="coerce")
        return d
    return pd.Series(pd.NaT, index=df.index)

# ----------------------------
# FIX FOR 2020–2025: Numeric-column metric mapping with auto offset
#
# Problem you hit:
# Newer files can have numbered columns "1","2","3",... but:
# - some years include Adjustment as column 1
# - some years start at A.1 as column 1 (Adjustment omitted), shifting everything
#
# Solution:
# - detect numeric columns by their header names
# - try two mappings:
#   offset=0: 1 -> METRICS_IN_ORDER[0] (includes Adjustment)
#   offset=1: 1 -> METRICS_IN_ORDER[1] (starts at A.1)
# - pick whichever produces more non-null values for anchor metrics
# ----------------------------
ANCHOR_METRICS = [
    "A. 1. Cases brought forward",
    "A. 2. Cases added during month",
    "A. 5. Cases carried forward",
    "B. 6. Total General Relief Cases",
    "E. Net General Relief Expenditure",
]

def choose_numeric_metric_mapping(df, numeric_cols, fname_for_log, logs):
    # Build two rename maps
    def build_map(offset):
        m = {}
        for col in numeric_cols:
            n = _norm(col)
            # extract leading int from "1" or "1 " etc.
            mobj = re.match(r"^(\d+)", n)
            if not mobj:
                continue
            k = int(mobj.group(1))  # 1-based
            idx = (k - 1) + offset
            if 0 <= idx < len(METRICS_IN_ORDER):
                m[col] = METRICS_IN_ORDER[idx]
        return m

    # Score mapping by how many non-null numeric values appear in anchor metrics
    def score_map(rename_map):
        tmp = df.rename(columns=rename_map)
        score = 0
        for am in ANCHOR_METRICS:
            if am in tmp.columns:
                v = pd.to_numeric(tmp[am], errors="coerce")
                score += int(v.notna().sum())
        return score

    map0 = build_map(offset=0)
    map1 = build_map(offset=1)

    score0 = score_map(map0) if map0 else -1
    score1 = score_map(map1) if map1 else -1

    if score1 > score0:
        logs.append(f"{fname_for_log}: numeric metric mapping chose OFFSET=1 (starts at A.1). scores: off0={score0}, off1={score1}")
        return map1
    else:
        logs.append(f"{fname_for_log}: numeric metric mapping chose OFFSET=0 (includes Adjustment). scores: off0={score0}, off1={score1}")
        return map0

def apply_metric_mapping(df, fname_for_log, logs):
    # If any canonical metric names already exist, leave them as-is.
    existing_named = [c for c in df.columns if any(c == m for m in METRICS_IN_ORDER)]
    # Identify purely numeric headers like "1","2",...
    numeric_cols = [c for c in df.columns if re.fullmatch(r"\d+", _norm(c))]

    if numeric_cols:
        # Choose the best numeric mapping (offset 0 vs 1)
        rename_map = choose_numeric_metric_mapping(df, numeric_cols, fname_for_log, logs)
        if rename_map:
            df = df.rename(columns=rename_map)

    # If there are NO numeric columns and NO named metrics, fall back to positional mapping after front fields
    metric_present = [m for m in METRICS_IN_ORDER if m in df.columns]
    if (not metric_present) and (not numeric_cols):
        known_front = [c for c in ["Date_Code", "Report_Month", "Month", "Year", "County_Name", "County_Code", "SFY", "FFY"] if c in df.columns]
        rest_cols = [c for c in df.columns if c not in known_front]
        rename_metrics = {}
        for j, c in enumerate(rest_cols):
            if j < len(METRICS_IN_ORDER):
                rename_metrics[c] = METRICS_IN_ORDER[j]
        if rename_metrics:
            df = df.rename(columns=rename_metrics)
            logs.append(f"{fname_for_log}: used positional metric mapping (no numeric headers found).")

    return df

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
            logs.append(f"{fname}: missing (put it next to app.py or in ./data/)")
            continue

        df, info = read_gr_file(path)
        if df is None or df.empty:
            logs.append(info)
            continue

        if "County_Name" not in df.columns:
            logs.append(f"{fname}: missing County_Name after read")
            continue

        # County cleanup: must contain at least one letter
        df["County_Name"] = df["County_Name"].astype(str).str.strip()
        df = df[df["County_Name"] != "Statewide"].copy()
        df = df.dropna(subset=["County_Name"]).copy()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()
        if df.empty:
            logs.append(f"{fname}: empty after county filtering")
            continue

        # Date
        df["Date"] = build_date(df)
        df = df.dropna(subset=["Date"]).copy()
        if df.empty:
            logs.append(f"{fname}: no parsable dates (Date_Code/Report_Month/Month+Year)")
            continue

        # >>> KEY FIX: robust metric mapping for 2020–2025 <<<
        df = apply_metric_mapping(df, fname, logs)

        metric_cols = [m for m in METRICS_IN_ORDER if m in df.columns]
        if not metric_cols:
            logs.append(f"{fname}: no metric columns recognized after mapping")
            continue

        # Numeric coercion
        for c in metric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=metric_cols, how="all").copy()
        if df.empty:
            logs.append(f"{fname}: all metric values empty after numeric coercion")
            continue

        # Long format
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
            + f" | long_rows={len(df_long):,}"
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
# MAIN (wrap so errors show)
# ----------------------------
try:
    # Preflight
    found = []
    missing = []
    for f in GR_FILE_NAMES:
        if resolve_path(f) is None:
            missing.append(f)
        else:
            found.append(f)

    with st.expander("Preflight (files found / missing)", expanded=show_debug):
        st.write("Looking in:", [str(d) for d in CANDIDATE_DIRS])
        st.write("**Found:**", found)
        st.write("**Missing:**", missing)

    data, logs = load_all(GR_FILE_NAMES)

    if show_debug:
        with st.expander("Debug log", expanded=True):
            for l in logs:
                st.write(l)

    if data.empty:
        st.error("No data loaded. Enable debug to see which files failed.")
        st.stop()

    min_date = data["Date"].min().date()
    max_date = data["Date"].max().date()
    st.write(f"**Loaded:** {len(data):,} rows • **Date range:** {min_date} → {max_date}")

    # Sidebar filters (default END = max_date so it shows through 2025)
    all_counties = sorted(data["County_Name"].unique().tolist())
    metrics = sorted(data["Metric"].unique().tolist(), key=metric_sort_key)

    with st.sidebar:
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
            default=["A. 1. Cases brought forward"]
            if "A. 1. Cases brought forward" in metrics
            else (["B. 6. Total General Relief Cases"] if "B. 6. Total General Relief Cases" in metrics else metrics[:1]),
        )

    # Filter
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

except Exception as e:
    st.error("The app crashed (this is why it looked blank). Here’s the error:")
    st.exception(e)
