import pandas as pd
import numpy as np
import os

def prepare_and_combine_gr_data(file_names):
    """
    Loads, cleans, and combines multiple GR data files into a single long-format DataFrame.
    """
    all_data_frames = []
    
    # Column mapping based on the identified structure (Row 4/Index 3 headers)
    metric_columns = {
        # County/Date Identifiers
        "Unnamed: 0": "Date_Code",
        "Unnamed: 1": "County_Name",
        "Unnamed: 3": "County_Code",
        "Unnamed: 6": "Report_Month",

        # Key Metrics (as identified in previous step)
        "CASES\nA": "Total GR Cases",
        "Unnamed: 15": "One-person Cases",
        "AMOUNT\nC": "Total GR Expenditure",
        "Net General Relief\nExpenditure": "Net GR Expenditure"
    }
    metrics_to_melt = ['Total GR Cases', 'One-person Cases', 'Total GR Expenditure', 'Net GR Expenditure']

    for file_name in file_names:
        print(f"Processing file: {file_name}")
        try:
            # 1. Load data with correct header
            df = pd.read_csv(file_name, header=3)

            # 2. Select and Rename Columns
            df = df.rename(columns=metric_columns)
            cols_to_keep = [col for col in metric_columns.values() if col in df.columns]
            df = df[cols_to_keep].copy()

            # 3. Data Cleaning and Preparation
            # Filter out "Statewide" and metadata rows
            df = df[df["County_Name"] != "Statewide"].copy()
            df = df.dropna(subset=['County_Name'])

            # Convert month string to datetime object
            df['Date'] = pd.to_datetime(df['Report_Month'], format='%b %Y', errors='coerce')
            df = df.dropna(subset=['Date'])
            
            # Convert metric columns to numeric
            for col in metrics_to_melt:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Drop rows where all key metrics are NaN after coercion
            df = df.dropna(subset=metrics_to_melt, how='all')

            # 4. Melt data to Long Format
            df_long = pd.melt(
                df,
                id_vars=['Date', 'Report_Month', 'County_Name', 'County_Code'],
                value_vars=metrics_to_melt,
                var_name='Metric',
                value_name='Value'
            )
            all_data_frames.append(df_long)

        except FileNotFoundError:
            print(f"ERROR: File not found: {file_name}. Skipping.")
        except Exception as e:
            print(f"ERROR processing {file_name}: {e}. Skipping.")

    # 5. Combine all dataframes
    if all_data_frames:
        df_combined = pd.concat(all_data_frames, ignore_index=True)
        # Sort by Date chronologically
        df_combined = df_combined.sort_values('Date').reset_index(drop=True)
        return df_combined
    else:
        return pd.DataFrame()

gr_file_list = [
    "16-17.csv",
    "17-18.csv",
    "17-18.csv",
    "18-19.csv",
    "19-20.csv",
    "20-21.csv",
    "21-22.csv",
    "22-23.csv",
    "23-24.csv",
    "24-25.csv",
]

# --- Execution ---
df_final_long = prepare_and_combine_gr_data(gr_file_list)

if not df_final_long.empty:
    # 6. Save the final prepared data to a CSV
    df_final_long.to_csv("gr_data_prepared.csv", index=False)
    print("\nSuccessfully combined all files and saved the data to 'gr_data_prepared.csv'.")
    print("You can now run the Streamlit app.")
else:
    print("\nNo data was successfully processed and combined. Please check the file names.")
