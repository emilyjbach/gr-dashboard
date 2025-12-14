import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import date
from pathlib import Path

# -----------------------------
# Page config (must be first)
# -----------------------------
st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Metric sort key (safe)
# -----------------------------
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

# -----------------------------
# File list
# -------------------------
