import streamlit as st
import pandas as pd
import altair as alt
import os
import re
from datetime import date

# --- Helper Function for Custom Metric Sorting ---
def metric_sort_key(metric_name):
    metric_name = str(metric_name)
    match = re.match(r'([A-E])[\.\s]*(\d+(\.\d+)?)?', metric_name)

    if match:
        main_letter = match.group(1)
        main_number_str = match.group(2)

        primary_sort = main_letter
        secondary_sort = 0
        tertiary_sort = 0

        if main_number_str:
            try:
                secondary_sort = float(main_number_str)
            except ValueError:
                secondary_sort = 999

        lower = metric_name.lower()
        if 'a.' in lower or ' a ' in lower:
            tertiary_sort = 1
        elif 'b.' in lower or ' b ' in lower:
            tertiary_sort = 2

        return (primary_sort, second_
