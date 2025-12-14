import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import date
from pathlib import Path
from typing import Optional, Tuple

# Altair silently truncates datasets > 5000 rows unless disabled
alt.data_transformers.disable_max_rows()

st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Always render something so “blank page” never happens silently
st.title("GR 237: General Relief")
st.caption("Use the sidebar filters. Toggle debug to see exactly what each CSV did during loading.")

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
# Header detection (brute-force header rows 0..120)
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

    numlike = 0
    for c in ncols:
        if re.fullmatch(r"\d+", c):
            numlike += 1
    if numlike >= 5:
        score += 2

    return score

def find_best_header_row(path, max_h=120):
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
    # require county + date-ish signal
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

    # Soft matches
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
        return None, f"{path.name}: could not find a plausible header row (scan 0–120)"

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

    out = out.fillna(pd.to_datetime(s.str.upper(), format="%b%y", errors="coerce"))

    num = pd.to_numeric(s, errors="coerce")
    idx = num.dropna().index
    if len(idx) > 0:
        yyyymm = num.loc[idx].astype(int).astype(str)
        out.loc[idx] = out.loc[idx].fillna(pd.to_datetime(yyyymm, format="%Y%m", errors="coerce"))

    for fmt in ("%Y-%m", "%Y-%m-%d", "%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
        out = out.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))

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
# CRITICAL FIX: Metric mapping for 2020–2025 using arithmetic constraints
#
# Why A.1 breaks:
# Newer files often have numeric headers "1","2","3"... but the numbering can be shifted
# (e.g., sometimes "1" is A.1, sometimes "1" is Adjustment). A naive offset guess is unreliable.
#
# Fix:
# Try multiple offsets and score them by how often GR identities hold:
#   A3 ≈ A1 + A2 (+ Adjustment if present)
#   A5 ≈ A3 - A4
#   B total cases ≈ family + one-person
#   B total persons ≈ family + one-person
#   B total expenditure ≈ cash + kind
# Choose the offset with the best constraint score, which pins A.1 correctly.
# ----------------------------
CONSTRAINTS = [
    # (lhs, [rhs terms], tolerance)
    ("A. 3. Total cases available", ["A. 1. Cases brought forward", "A. 2. Cases added during month"], 2.0),  # plus optional Adjustment handled separately
    ("A. 5. Cases carried forward", ["A. 3. Total cases available", "A. 4. Cases discontinued"], 2.0),       # carried = total - discontinued
    ("B. 6. Total General Relief Cases", ["B. 6a. Family Cases", "B. 6b. One-person Cases"], 2.0),
    ("B. 6. Total General Relief Persons", ["B. 6a. Family Persons", "B. 6b. One-person Persons"], 2.0),
    ("B. 6. Total GR Expenditure", ["B. 6(1). Amount in Cash", "B. 6(2). Amount in Kind"], 5.0),
]

def _to_num(s):
    return pd.to_numeric(s, errors="coerce")

def _constraint_score(tmp):
    satisfied = 0
    possible = 0

    for lhs, rhs_terms, tol in CONSTRAINTS:
        if lhs not in tmp.columns:
            continue

        # Special-case A3 equation: optionally include Adjustment if present
        if lhs == "A. 3. Total cases available":
            need = [lhs] + rhs_terms
            if any(c not in tmp.columns for c in need):
                continue

            lhs_v = _to_num(tmp[lhs])
            a1 = _to_num(tmp[rhs_terms[0]])
            a2 = _to_num(tmp[rhs_terms[1]])

            # compare both with and without Adjustment; whichever is closer per-row
            if "A. Adjustment" in tmp.columns:
                adj = _to_num(tmp["A. Adjustment"])
                rhs_with = a1 + a2 + adj
                rhs_without = a1 + a2
                ok = lhs_v.notna() & a1.notna() & a2.notna()
                if ok.any():
                    diff_with = (lhs_v - rhs_with).abs()
                    diff_without = (lhs_v - rhs_without).abs()
                    diff = diff_with.where(diff_with <= diff_without, diff_without)
                    possible += int(ok.sum())
                    satisfied += int(((diff <= tol) & ok).sum())
            else:
                rhs = a1 + a2
                ok = lhs_v.notna() & a1.notna() & a2.notna()
                if ok.any():
                    diff = (lhs_v - rhs).abs()
                    possible += int(ok.sum())
                    satisfied += int(((diff <= tol) & ok).sum())
            continue

        # Generic: either lhs == sum(rhs) OR for carried-forward: lhs == rhs0 - rhs1
        if any(c not in tmp.columns for c in [lhs] + rhs_terms):
            continue

        lhs_v = _to_num(tmp[lhs])
        r0 = _to_num(tmp[rhs_terms[0]])
        r1 = _to_num(tmp[rhs_terms[1]])

        ok = lhs_v.notna() & r0.notna() & r1.notna()
        if not ok.any():
            continue

        if lhs == "A. 5. Cases carried forward":
            rhs = r0 - r1
        else:
            rhs = r0 + r1

        diff = (lhs_v - rhs).abs()
        possible += int(ok.sum())
        satisfied += int(((diff <= tol) & ok).sum())

    # also reward having lots of non-null A.1 (prevents weird “perfect score on tiny overlap”)
    if "A. 1. Cases brought forward" in tmp.columns:
        a1nn = int(_to_num(tmp["A. 1. Cases brought forward"]).notna().sum())
    else:
        a1nn = 0

    return satisfied, possible, a1nn

def choose_numeric_mapping_by_constraints(df, numeric_cols, logs, fname):
    # Try offsets around where we expect the block to start.
    # offset=0 means "1" -> METRICS_IN_ORDER[0] (Adjustment)
    # offset=1 means "1" -> METRICS_IN_ORDER[1] (A.1)
    candidates = list(range(-2, 6))  # broader than just 0/1

    best = None
    best_tuple = (-1, -1, -1)  # (satisfied, possible, a1nn)

    for offset in candidates:
        rename_map = {}
        for col in numeric_cols:
            m = re.match(r"^(\d+)$", _norm(col))
            if not m:
                continue
            k = int(m.group(1))  # 1-based
            idx = (k - 1) + offset
            if 0 <= idx < len(METRICS_IN_ORDER):
                rename_map[col] = METRICS_IN_ORDER[idx]

        if not rename_map:
            continue

        tmp = df.rename(columns=rename_map)

        sat, poss, a1nn = _constraint_score(tmp)

        # Choose by: highest satisfied; tie-break by possible; tie-break by a1nn
        key = (sat, poss, a1nn)
        if key > best_tuple:
            best_tuple = key
            best = rename_map

    if best is None:
        logs.append(f"{fname}: numeric mapping failed (no viable offsets)")
        return {}

    logs.append(f"{fname}: numeric mapping chosen via constraints: satisfied={best_tuple[0]}, possible={best_tuple[1]}, A.1 nonnull={best_tuple[2]}")
    return best

def apply_metric_mapping(df, fname, logs):
    # Prefer numeric headers if present (most reliable for 20-21+)
    numeric_cols = [c for c in df.columns if re.fullmatch(r"\d+", _norm(c))]
    if numeric_cols:
        rename = choose_numeric_mapping_by_constraints(df, numeric_cols, logs, fname)
        if rename:
            df = df.rename(columns=rename)

    # If still no canonical metrics, fall back to positional mapping
    metric_present = [m for m in METRICS_IN_ORDER if m in df.columns]
    if not metric_present:
        known_front = [c for c in ["Date_Code", "Report_Month", "Month", "Year", "County_Name", "County_Code", "SFY", "FFY"] if c in df.columns]
        rest_cols = [c for c in df.columns if c not in known_front]
        rename_metrics = {}
        for j, c in enumerate(rest_cols):
            if j < len(METRICS_IN_ORDER):
                rename_metrics[c] = METRICS_IN_ORDER[j]
        if rename_metrics:
            df = df.rename(columns=rename_metrics)
            logs.append(f"{fname}: used positional metric mapping (fallback).")

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

        df["County_Name"] = df["County_Name"].astype(str).str.strip()
        df = df[df["County_Name"] != "Statewide"].copy()
        df = df.dropna(subset=["County_Name"]).copy()
        df = df[df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))].copy()
        if df.empty:
            logs.append(f"{fname}: empty after county filtering")
            continue

        df["Date"] = build_date(df)
        df = df.dropna(subset=["Date"]).copy()
        if df.empty:
            logs.append(f"{fname}: no parsable dates")
            continue

        # >>> KEY FIX FOR A.1 in 2020–2025 <<<
        df = apply_metric_mapping(df, fname, logs)

        metric_cols = [m for m in METRICS_IN_ORDER if m in df.columns]
        if not metric_cols:
            logs.append(f"{fname}: no metric columns recognized after mapping")
            continue

        for c in metric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=metric_cols, how="all").copy()
        if df.empty:
            logs.append(f"{fname}: all metric values empty after numeric coercion")
            continue

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
# MAIN (wrapped so errors show in the app)
# ----------------------------
try:
    # Preflight
    found = []
    missing = []
    for f in GR_FILE_NAMES:
        (found if resolve_path(f) else missing).append(f)

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

    # Sidebar filters (default END = max_date so it goes through 2025 automatically)
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

except Exception as e:
    st.error("The app crashed (this is why it looked blank). Here’s the error:")
    st.exception(e)
