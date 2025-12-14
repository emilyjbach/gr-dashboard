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

# ----------------------------
# Metric sorting
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

BASE_DIR = Path(__file__).resolve().parent
CANDIDATE_DIRS = [BASE_DIR, BASE_DIR / "data"]

def resolve_path(fname: str) -> Optional[Path]:
    for d in CANDIDATE_DIRS:
        p = d / fname
        if p.exists():
            return p
    return None

# ----------------------------
# Canonical metric order for GR237
# (maps numbered columns 1..N by position after fixed front fields)
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
# Robust header detection (works for 20-21 .. 24-25 too)
#
# Why your 20-21+ failed:
# Those files often DON'T have the header row exactly "Date,Month,Year,County..."
# Sometimes it's "Report Month, County Name, ..." or has leading blanks / different ordering.
#
# Strategy:
# 1) Read a probe as raw rows (engine="python") to handle multiline quoted headers.
# 2) Score each row based on presence of key header tokens anywhere in the row.
# 3) Pick the best-scoring row if it contains BOTH a county token and a date/month token.
# 4) If that fails, brute-force try header positions 0..30 and pick the first that yields expected columns.
# ----------------------------
HEADER_TOKENS_DATE = {
    "date", "date_code", "date code", "report_month", "report month", "month", "year"
}
HEADER_TOKENS_COUNTY = {
    "county", "county_name", "county name", "county_code", "county code"
}
HEADER_TOKENS_OTHER = {"sfy", "ffy"}

def _norm_cell(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip().lstrip("\ufeff").strip().lower()

def detect_header_row_by_scoring(path: Path, max_probe_rows: int = 250) -> Optional[int]:
    try:
        probe = pd.read_csv(path, header=None, engine="python", nrows=max_probe_rows)
    except Exception:
        return None

    best_i = None
    best_score = -1

    for i in range(len(probe)):
        row = probe.iloc[i].tolist()
        cells = [_norm_cell(c) for c in row]
        cellset = set([c for c in cells if c])

        # Presence checks (any match, not exact position)
        has_county = any(any(tok in c for tok in ["county"]) for c in cellset) or any(c in HEADER_TOKENS_COUNTY for c in cellset)
        has_dateish = any(c in HEADER_TOKENS_DATE for c in cellset) or any("report" in c and "month" in c for c in cellset)

        # Score: count exact token hits + useful signals
        score = 0
        score += sum(1 for c in cellset if c in HEADER_TOKENS_DATE)
        score += sum(1 for c in cellset if c in HEADER_TOKENS_COUNTY)
        score += sum(1 for c in cellset if c in HEADER_TOKENS_OTHER)

        # Bonus: if row contains a run of numeric column headers like 1,2,3...
        numlike = 0
        for c in cellset:
            if re.fullmatch(r"\d+", c):
                numlike += 1
        if numlike >= 5:
            score += 2

        # Only consider rows that look like a header row (must contain county + date-ish)
        if has_county and has_dateish and score > best_score:
            best_score = score
            best_i = i

    return best_i

def _looks_like_expected_columns(cols) -> bool:
    normed = [_norm_cell(c) for c in cols]
    joined = " ".join(normed)
    # we need a county column and some date/month indicator
    has_county = ("county" in joined)
    has_dateish = ("date" in joined) or ("report month" in joined) or ("report_month" in joined) or ("month" in joined)
    return has_county and has_dateish

def read_gr_file(path: Path) -> Tuple[Optional[pd.DataFrame], str]:
    base = path.name

    header_row = detect_header_row_by_scoring(path)
    if header_row is not None:
        try:
            df = pd.read_csv(path, header=header_row, engine="python")
            # normalize
            df = normalize_columns(df)
            if "County_Name" in df.columns and ("Date_Code" in df.columns or "Report_Month" in df.columns or ("Month" in df.columns and "Year" in df.columns)):
                return df, f"{base}: header row {header_row}"
        except Exception:
            pass  # fall through to brute force

    # Brute-force fallback: try header rows 0..30 and pick first that yields expected columns
    for h in range(0, 31):
        try:
            df_try = pd.read_csv(path, header=h, engine="python")
            if _looks_like_expected_columns(df_try.columns):
                df_try = normalize_columns(df_try)
                return df_try, f"{base}: header row {h} (fallback scan)"
        except Exception:
            continue

    return None, f"{base}: could not find header row (scored + fallback scan failed)"

# ----------------------------
# Column normalization (handles different year formats)
# ----------------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}

    for c in df.columns:
        cn = str(c).strip().lstrip("\ufeff").strip()

        low = cn.lower()

        # Date
        if low == "date" or low == "date_code" or low == "date code":
            rename_map[c] = "Date_Code"
        elif low in ("report_month", "report month", "reportmonth"):
            rename_map[c] = "Report_Month"

        # County name/code
        elif low in ("county", "county_name", "county name"):
            rename_map[c] = "County_Name"
        elif low in ("county_code", "county code"):
            rename_map[c] = "County_Code"

        # Month/Year/SFY/FFY (when present)
        elif low == "month":
            rename_map[c] = "Month"
        elif low == "year":
            rename_map[c] = "Year"
        elif low == "sfy":
            rename_map[c] = "SFY"
        elif low == "ffy":
            rename_map[c] = "FFY"

    df = df.rename(columns=rename_map)

    # Some exports have "County Name " with extra spaces etc. Try soft matching if still missing.
    if "County_Name" not in df.columns:
        for c in df.columns:
            if "county" in _norm_cell(c) and "name" in _norm_cell(c):
                df = df.rename(columns={c: "County_Name"})
                break
        if "County_Name" not in df.columns:
            for c in df.columns:
                if _norm_cell(c) == "county":
                    df = df.rename(columns={c: "County_Name"})
                    break

    if "Date_Code" not in df.columns and "Report_Month" not in df.columns:
        for c in df.columns:
            if _norm_cell(c) in ("date", "date_code", "date code"):
                df = df.rename(columns={c: "Date_Code"})
                break
            if "report" in _norm_cell(c) and "month" in _norm_cell(c):
                df = df.rename(columns={c: "Report_Month"})
                break

    return df

# ----------------------------
# Date building (robust)
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
    # Prefer Date_Code
    if "Date_Code" in df.columns:
        d = parse_date_series(df["Date_Code"])
        if d.notna().any():
            return d

    # Then Report_Month (common in newer years)
    if "Report_Month" in df.columns:
        d = parse_date_series(df["Report_Month"])
        if d.notna().any():
            return d

    # Then Month+Year
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
            retur
