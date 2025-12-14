import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import date
from pathlib import Path

# ----------------------------
# Helper: Custom Metric Sorting
# ----------------------------
def metric_sort_key(metric_name):
    match = re.match(r'([A-E])[\.\s]*(\d+(\.\d+)?)?', str(metric_name))

    if match:
        main_letter = match.group(1)
        main_number = match.group(2)

        primary = main_letter
        secondary = float(main_number) if main_number else 0.0
        tertiary = 0

        m = str(metric_name).lower()
        if 'a.' in m or ' a ' in m:
            tertiary = 1
        elif 'b.' in m or ' b ' in m:
            tertiary = 2

        retu
