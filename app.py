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
    initial_sidebar_state="expanded",
)

# ---------------------------------
# Safe metric sorting (never throws)
# ---------------------------------
def metric_sort_key(metric_name: str):
    """
    Robust bureaucratic metric sorter.
    Sorts by leading letter (A–E), then first number found, then a/b suffix.
    """
    name = str(metric_name)

    letter_match = re.match(r"^\s*([A-E])", name)
    letter = letter_match.group(1) if letter_match else "Z"

    # First integer anywhere in the string (handles "6a", "6(1)", etc.)
    num_match = re.search(r"(\d+)", name)
    number = int(num_match.group(1)) if num_match else 0

    sub = 0
    lower = name.lower()
    # Prefer explicit ". 6a." style, but also tolerate " a " variants
    if re.search(r"\b6a\b", lower) or "a." in lower or " a " in lower:
        sub = 1
    if re.search(r"\b6b\b", lower) or "b." in lower or " b " in lower:
        sub = 2

    return (letter, number, sub)

# ---------------------------------
# File list fallback
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
# Cached data loader
# ---------------------------------
@st.cache_data
def prepare_and_combine_gr_data(file_paths: tuple[str, ...]):
    logs: list[str] = []
    all_frames: list[pd.DataFrame] = []

    # Covers the common GR 237 variants including 19–20 quirks
    DATE_FORMATS = [
        None,          # pandas auto
        "%Y%m",        # 201507
        "%Y-%m",       # 2019-07
        "%Y-%m-%d",    # 2019-07-01
        "%m/%Y",       # 07/2019
        "%m/%d/%Y",    # 07/01/2019
        "%b%y",        # Jul19
        "%b-%y",       # Jul-19
    ]

    # Mapping based on header=4 files
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

    # County must be "alphanumeric" (letters/numbers, spaces, common punctuation),
    # AND must include at least one letter (so "123" or "2020" doesn't slip in).
    county_allowed = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-\'\.]*$")
    county_has_letter = re.compile(r"[A-Za-z]")

    for path_str in file_paths:
        p = Path(path_str)
        if not p.exists():
            logs.append(f"⚠️ Missing file: {p.name}")
            continue

        try:
            df = pd.read_csv(p, header=4)

            # Rename columns by position
            df.columns = [column_index_map.get(i, col) for i, col in enumerate(df.columns)]

            # Keep only known columns
            keep_cols = [c for c in column_index_map.values() if c in df.columns]
            df = df[keep_cols].copy()

            # Drop "Statewide" and null counties
            if "County_Name" not in df.columns:
                logs.append(f"⚠️ {p.name}: missing County_Name column after mapping")
                continue

            df = df[df["County_Name"] != "Statewide"].copy()
            df = df.dropna(subset=["County_Name"]).copy()

            # County cleaning: enforce "alphanumeric" + at least one letter
            df["County_Name"] = df["County_Name"].astype(str).str.strip()

            before_cnt = len(df)
            df = df[df["County_Name"].apply(lambda x: bool(county_allowed.match(x)) and bool(county_has_letter.search(x)))].copy()
            removed = before_cnt - len(df)
            if removed > 0:
                logs.append(f"ℹ️ {p.name}: removed {removed} non-alphanumeric/
