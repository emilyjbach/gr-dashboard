import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import date
from pathlib import Path

# ---------------------------------
# Page config (must be first)
# ---------------------------------
st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------
# Safe metric sorting
# ---------------------------------
def metric_sort_key(metric_name):
    name = str(metric_name)

    letter_match = re.match(r"^\s*([A-E])", name)
    letter = letter_match.group(1) if letter_match else "Z"

    num_match = re.search(r"(\d+)", name)
    number = int(num_match.group(1)) if num_match else 0

    sub = 0
    lower = name.lower()
    if "a." in lower or " a " in lower:
        sub = 1
    elif "b." in lower or " b " in lower:
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
# Cached data loader
# ---------------------------------
@st.cache_data
def prepare_and_combine_gr_data(file_paths):
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
        16: "B. 6. Total G
