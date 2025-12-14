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

st.write("🚀 App started successfully")  # hard render guard


# ---------------------------------
# Safe metric sorting (FIXED)
# ---------------------------------
def metric_sort_key(metric_name):
    """
    Robust bureaucratic metric sorter.
    NEVER throws.
    """
    name = str(metric_name)

    match = re.match(r'([A-E])', name)
    letter = match.group(1) if match else "Z"

    num_match = re.search(r'(\d+)', name)
    number = int(num_match.group(1)) if num_match else 0

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
# Data loader (NO silent failure)
# ---------------------------------
@st.cach
