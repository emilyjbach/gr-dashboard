import re
from datetime import date
from pathlib import Path
from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st

alt.data_transformers.disable_max_rows()

st.set_page_config(
    page_title="General Relief (GR) Interactive Database",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    
      .block-container { padding-top: 1.1rem; padding-bottom: 1.3rem; max-width: 1220px; }
      h1 { letter-spacing: -0.03em; margin-bottom: 0.15rem; }
      [data-testid="stCaptionContainer"] { margin-top: 0.2rem; opacity: 0.85; }

      /* sidebar */
      section[data-testid="stSidebar"] { border-right: 1px solid rgba(49,51,63,0.12); }
      section[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }
      section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 { letter-spacing: -0.02em; }

      /* silly girly pop box */
      .gr-hero {
        position: relative;
        overflow: hidden;
        border-radius: 18px;
        padding: 18px 18px 16px 18px;
        border: 1px solid rgba(49, 51, 63, 0.14);
        background:
          radial-gradient(900px 180px at 10% 0%, rgba(151, 71, 255, 0.16), transparent 55%),
          radial-gradient(900px 180px at 60% 10%, rgba(0, 209, 255, 0.14), transparent 55%),
          radial-gradient(700px 200px at 90% 0%, rgba(255, 97, 165, 0.14), transparent 58%),
          rgba(255,255,255,0.70);
        box-shadow: 0 10px 30px rgba(0,0,0,0.06);
      }
      .gr-hero:after{
        content:"";
        position:absolute;
        inset:-2px;
        border-radius: 18px;
        background: linear-gradient(120deg,
          rgba(151,71,255,0.22),
          rgba(0,209,255,0.18),
          rgba(255,97,165,0.18));
        filter: blur(22px);
        opacity: 0.55;
        z-index: 0;
      }
      .gr-hero * { position: relative; z-index: 1; }
      .gr-hero-title {
        font-size: 1.02rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0 0 0.35rem 0;
      }
      .gr-hero-sub {
        font-size: 0.92rem;
        opacity: 0.80;
        margin: 0;
      }
      .pill-row { margin-top: 0.8rem; display: flex; flex-wrap: wrap; gap: 10px; }
      .pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        border-radius: 999px;
        border: 1px solid rgba(49, 51, 63, 0.16);
        background: rgba(255,255,255,0.72);
        box-shadow: 0 1px 10px rgba(0,0,0,0.04);
        font-size: 0.88rem;
      }
      .dot {
        width: 9px;
        height: 9px;
        border-radius: 999px;
        display:inline-block;
        background: linear-gradient(135deg, rgba(151,71,255,0.95), rgba(0,209,255,0.9));
      }
      .dot2 { background: linear-gradient(135deg, rgba(255,97,165,0.95), rgba(255,184,107,0.9)); }
      .dot3 { background: linear-gradient(135deg, rgba(0,209,255,0.9), rgba(57,255,20,0.55)); }

      /* make buttons/toggles feel more modern */
      .stButton button, .stDownloadButton button {
        border-radius: 12px !important;
        padding: 0.45rem 0.9rem !important;
      }

      /* subheadr */
      h2, h3 { letter-spacing: -0.02em; }

      /* divs */
      hr { margin: 1.35rem 0; opacity: 0.45; }
    </style>
    """,
    unsafe_allow_html=True,
)
# end styling


st.title("General Relief")
st.caption(
    "Emily Bach (Development, Visualization) | CDSS (Data) | Language: Python | Last Code Update: 12/14/2025 Last Data Pull: 12/12/2025"
)

# files
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

# metrics
METRICS_IN_ORDER = [
    "A. Adjustment",
    "A. 1. Cases brought forward",
    "A. 2. Cases added during month",
    "A. 3. Total cases available",
    "A. 4. Cases discontinued",
    "A. 5. Cases carried forward",
    "B. 6. Total General Relief Cases",
    "B. 6a. Total Family Cases",
    "B. 6b. Total One-person Cases",
    "B. 6. Total General Relief Persons",
    "B. 6a. Total Family Case Persons",
    "B. 6b. Total One-person Case Persons",
    "B. 6. Total GR Expenditure (Dollars)",
    "B. 6(1). GR Expenditure in Cash",
    "B. 6(2). GR Expenditure in Kind",
    "B. 6a. Total Family Expenditure (Dollars)",
    "B. 6b. Total One-person Expenditure (Dollars)",
    "C. 7. Cases added during month",
    "C. 8. Total SSA checks disposed of",
    "C. 8a. Total SSA disposed in 1-10 days",
    "C. 9. SSA sent SSI/SSP check directly to receipient",
    "C. 10. Denial notice received",
    "D. 11. Reimbursements Cases",
    "D. 11a. SSA check received Cases",
    "D. 11b. Repaid by recipient Cases",
    "D. 11. Amount reimbursed",
    "D. 11a. Amount received in SSA check",
    "D. 11b. Amount repaid by recipient",
    "E. Net General Relief Expenditure",
]

# sidebar
with st.sidebar:
    st.header("Filter Options")
    show_debug = st.checkbox("Show debug log", value=False)


# helpers
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


def base_dir() -> Path:
    try:
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()


BASE_DIR = base_dir()
CANDIDATE_DIRS = [BASE_DIR, BASE_DIR / "data"]


def resolve_path(fname: str) -> Optional[Path]:
    for d in CANDIDATE_DIRS:
        p = d / fname
        if p.exists():
            return p
    return None


def norm_col(x) -> str:
    return str(x).strip().lstrip("\ufeff").strip()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # drop spacer cols
    drop_cols = []
    for c in df.columns:
        s = norm_col(c)
        if s == "" or s.lower().startswith("unnamed"):
            drop_cols.append(c)
        elif s.strip() == "":
            drop_cols.append(c)
    if drop_cols:
        df = df.drop(columns=drop_cols, errors="ignore")

    # standardize col nams
    rename_map = {}
    for c in df.columns:
        low = norm_col(c).lower()
        if low in ("date", "date code", "date_code"):
            rename_map[c] = "Date_Code"
        elif low in ("county name", "county_name", "county"):
            rename_map[c] = "County_Name"
        elif low in ("county code", "county_code"):
            rename_map[c] = "County_Code"
        elif low in ("report month", "report_month"):
            rename_map[c] = "Report_Month"
        elif low == "month":
            rename_map[c] = "Month"
        elif low == "year":
            rename_map[c] = "Year"
        elif low == "sfy":
            rename_map[c] = "SFY"
        elif low == "ffy":
            rename_map[c] = "FFY"

    return df.rename(columns=rename_map)


def parse_date_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)

    out = pd.Series(pd.NaT, index=s.index)

    # mon12
    out = out.fillna(pd.to_datetime(s.str.upper(), format="%b%y", errors="coerce"))

    # 202512
    num = pd.to_numeric(s, errors="coerce")
    idx = num.dropna().index
    if len(idx) > 0:
        yyyymm = num.loc[idx].astype(int).astype(str)
        out.loc[idx] = out.loc[idx].fillna(
            pd.to_datetime(yyyymm, format="%Y%m", errors="coerce")
        )

    # other randos
    for fmt in ("%Y-%m", "%Y-%m-%d", "%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
        out = out.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))

    # fin
    out = out.fillna(pd.to_datetime(s, errors="coerce"))
    return out


def build_date(df: pd.DataFrame) -> pd.Series:
    # pref dat
    if "Date_Code" in df.columns:
        d = parse_date_series(df["Date_Code"])
        if d.notna().any():
            return d

    # else
    if "Report_Month" in df.columns:
        d = parse_date_series(df["Report_Month"])
        if d.notna().any():
            return d

    # else
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


def read_gr_csv(path: Path, logs: list[str]) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path, header=4, engine="python")
        df = normalize_columns(df)
        if "County_Name" in df.columns and (
            "Date_Code" in df.columns or "Report_Month" in df.columns
        ):
            logs.append(f"{path.name}: read with header=4")
            return df
    except Exception as e:
        logs.append(f"{path.name}: header=4 failed ({e})")

    for h in range(0, 51):
        try:
            df = pd.read_csv(path, header=h, engine="python")
            df = normalize_columns(df)
            cols = " ".join([norm_col(c).lower() for c in df.columns])
            if ("county" in cols) and (
                ("date" in cols) or ("report month" in cols) or ("report_month" in cols)
            ):
                logs.append(f"{path.name}: read with header={h} (fallback)")
                return df
        except Exception:
            continue

    logs.append(f"{path.name}: could not find usable header row")
    return None


def map_metric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    A.1. fix
    """
    rename = {}
    for c in df.columns:
        s = norm_col(c)
        m = re.match(r"^(?:Cell\s*)?(\d+)$", s, flags=re.IGNORECASE)
        if not m:
            continue
        n = int(m.group(1))
        if 1 <= n <= len(METRICS_IN_ORDER):
            rename[c] = METRICS_IN_ORDER[n - 1]
    if rename:
        df = df.rename(columns=rename)
    return df


@st.cache_data
def load_all(files: list[str]):
    logs: list[str] = []
    frames: list[pd.DataFrame] = []
    county_has_letter = re.compile(r"[A-Za-z]")

    for fname in files:
        path = resolve_path(fname)
        if path is None:
            logs.append(f"{fname}: missing (put next to app.py or in ./data/)")
            continue

        df = read_gr_csv(path, logs)
        if df is None or df.empty:
            continue

        # req!!!!!
        if "County_Name" not in df.columns:
            logs.append(f"{fname}: missing County_Name after read")
            continue

        # clean county
        df["County_Name"] = df["County_Name"].astype(str).str.strip()
        df = df[df["County_Name"] != "Statewide"].copy()
        df = df.dropna(subset=["County_Name"]).copy()
        df = df[
            df["County_Name"].apply(lambda x: bool(county_has_letter.search(x)))
        ].copy()
        if df.empty:
            logs.append(f"{fname}: empty after county filtering")
            continue

        # date builder
        df["Date"] = build_date(df)
        df = df.dropna(subset=["Date"]).copy()
        if df.empty:
            logs.append(f"{fname}: no parsable dates")
            continue

        # good code! go good code!
        if "Report_Month" not in df.columns:
            df["Report_Month"] = df["Date"].dt.strftime("%b %Y")

        # a.1. fix r2
        logs.append(f"{fname}: Columns before mapping: {df.columns.tolist()}") # <<< ADD THIS LINE
        df = map_metric_columns(df)

        metric_cols = [m for m in METRICS_IN_ORDER if m in df.columns]
        if not metric_cols:
            logs.append(
                f"{fname}: no metric columns recognized (expected 1..29 or Cell 1..29)"
            )
            continue

        # num coerc
        for c in metric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=metric_cols, how="all").copy()
        if df.empty:
            logs.append(f"{fname}: all metric values empty after numeric coercion")
            continue

        # long
        id_vars = ["Date", "Report_Month", "County_Name"]
        if "County_Code" in df.columns:
            id_vars.append("County_Code")

        df_long = pd.melt(
            df,
            id_vars=id_vars,
            value_vars=metric_cols,
            var_name="Metric",
            value_name="Value",
        ).dropna(subset=["Value"]).copy()

        frames.append(df_long)
        logs.append(
            f"{fname}: long_rows={len(df_long):,} | {df['Date'].min().date()} → {df['Date'].max().date()}"
        )

    if not frames:
        return pd.DataFrame(), logs

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("Date").reset_index(drop=True)
    combined = combined.drop_duplicates(
        subset=["Date", "County_Name", "Metric"], keep="first"
    )
    return combined, logs


try:
    data, logs = load_all(GR_FILE_NAMES)

    if show_debug:
        with st.expander("Debug log", expanded=True):
            st.write("Looking in:", [str(d) for d in CANDIDATE_DIRS])
            for l in logs:
                st.write(l)

    if data.empty:
        st.error(
            "No data loaded. Turn on the debug log to see which file(s) failed and why."
        )
        st.stop()

    min_date = data["Date"].min().date()
    max_date = data["Date"].max().date()

    # styling hero
    st.markdown(
        f"""
        <div class="gr-hero">
          <div class="gr-hero-title">GR 237 - General Relief and Interim Assistance to Applicants for SSI/SSP Monthly Caseload and Expenditure Statistical Report</div>
          <p class="gr-hero-sub">Source Data: https://www.cdss.ca.gov/inforesources/research-and-data/disability-adult-programs-data-tables/gr-237</p>
          <div class="pill-row">
            <span class="pill"><span class="dot"></span><b>Rows</b>&nbsp;{len(data):,}</span>
            <span class="pill"><span class="dot dot2"></span><b>Date range</b>&nbsp;{min_date} → {max_date}</span>
            <span class="pill"><span class="dot dot3"></span><b>Files</b>&nbsp;{len(GR_FILE_NAMES)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height: 0.9rem;'></div>", unsafe_allow_html=True)
    # hero end

    # sidebar filters
    all_counties = sorted(data["County_Name"].unique().tolist())
    metrics = sorted(data["Metric"].unique().tolist(), key=metric_sort_key)

    with st.sidebar:
        default_start = max(min_date, date(2017, 1, 1))
        default_end = max_date  # show through 2025 if those files load

        date_range = st.slider(
            "Date Range",
            min_value=min_date,
            max_value=max_date,
            value=(default_start, default_end),
            format="YYYY/MM/DD",
        )

        says_default_counties = ["Contra Costa", "Kern"]
        default_counties = [c for c in says_default_counties if c in all_counties]
        if not default_counties:
            default_counties = all_counties[:2]

        selected_counties = st.multiselect(
            "Counties",
            options=all_counties,
            default=default_counties,
        )

        default_metric = "A. 2. Cases added during month"
        selected_metrics = st.multiselect(
            "Metrics",
            options=metrics,
            default=[default_metric]
            if default_metric in metrics
            else (metrics[:1] if metrics else []),
        )

    # filtered view
    data_dated = data[
        (data["Date"].dt.date >= date_range[0])
        & (data["Date"].dt.date <= date_range[1])
    ].copy()

    df = data_dated[
        data_dated["County_Name"].isin(selected_counties)
        & data_dated["Metric"].isin(selected_metrics)
    ].dropna(subset=["Value"]).copy()

    if df.empty:
        st.warning("No data for the selected filters.")
        st.stop()

    df["Series"] = df["County_Name"] + " - " + df["Metric"]

    # (counties + metrics + date range) 
    county_plural = "Counties" if len(selected_counties) > 1 else "County"

    counties_label = ", ".join(selected_counties[:4]) + (
        "…" if len(selected_counties) > 4 else ""
    )
    metrics_label = ", ".join(selected_metrics[:4]) + (
    "…" if len(selected_metrics) > 4 else ""
    )

    start_label = date_range[0].strftime("%Y/%m/%d")
    end_label = date_range[1].strftime("%Y/%m/%d")

    st.markdown(
        f"""
        <h3 style='margin: 0.2rem 0 0.25rem 0;'>{county_plural}: {counties_label}</h3>
        <div style="opacity:0.82; font-size:0.95rem; margin-bottom:0.6rem;">
            <b>Metrics:</b> {metrics_label} &nbsp; 
            <b>Period:</b> {start_label} → {end_label}
        </div>
        """,
        unsafe_allow_html=True,
    )
    # end title big guy

    chart_title = (
        f"{county_plural}: {counties_label} | {metrics_label} | {start_label} → {end_label}"
    )

    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("Date:T", axis=alt.Axis(title="Report Month", format="%b %Y")),
            y=alt.Y("Value:Q", scale=alt.Scale(zero=False), title="Value"),
            color=alt.Color("Series:N"),
            tooltip=[
                alt.Tooltip("Report_Month:N"),
                alt.Tooltip("County_Name:N"),
                alt.Tooltip("Metric:N"),
                alt.Tooltip("Value:Q", format=",.0f"),
            ],
        )
        .properties(title=chart_title)
        .interactive()
    )

    st.altair_chart(chart, use_container_width=True)

    st.markdown("---")
    st.markdown(
        "<h3 style='margin-bottom: 0.2rem;'>Underlying Data</h3>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Tip: Columns are sortable; to multi-sort pin a column. This is likely most helpful for multi-county or multi-metric reports. Copied data exports as .csv."
    )

    st.dataframe(df.drop(columns=["Series", "County_Code", "Date"], errors="ignore"))

    st.markdown("---")
    st.markdown(
            "<h3 style='margin-bottom: 0.2rem;'>Interpreting Data</h3>",
            unsafe_allow_html=True,
    )

    st.caption("GR 237 is a monthly report produced by the California Department of Social Services (CDSS) documenting county-level data changes in General Relief and Interim Assistance cases. These programs provide cash benefits to thousands of Californians each month.")
    
    st.caption(
        "There are no strict rules for interpreting GR 237 data and local sources with a direct tie to impacted communities should be consulted for a full explanation of trends. The Roots Community Health Center, for example, prepared an **[excellent report](https://rootscommunityhealth.org/wp-content/uploads/2014/07/GA_eval_12.pdf)** utilizing and contextualizing data trends in Alameda County's GA Program (which itself recommends a dashboard like this one.)",
        unsafe_allow_html=True,
    )

    st.caption("Still, in general, major shifts in month-to-month data are rare and warrant specific explanation. For investigations into major data changes, viewers should check the y-axis range, where the minimum is the minimum data point, not zero.") 

    st.caption("Beginning in March 2020, CDSS adopted **[a policy](https://www.cdss.ca.gov/portals/9/Data%20De-Identification%20Guidelines%20DSS%20Reference%20Guide_FINAL.pdf)** that replaced values 1-11 with a * (star) for sensitive caseload metrics, which here, includes all non-dollar metrics. CDSS instituted these changes, known as de-identification, to safeguard privacy rights. De-identification has **[widely-appreciated](https://pmc.ncbi.nlm.nih.gov/articles/PMC8110889/)** **[racial equity](https://healthlaw.org/wp-content/uploads/2023/03/Striking-the-Balance_for-publication.pdf)** **[benefits](https://aisp.upenn.edu/wp-content/uploads/2025/02/Centering-Equity-Toolkit-2.0.pdf)** in the context of public data sets without demographic information, like GR 237.",
    unsafe_allow_html=True,
              )

    st.caption("All data prior to 2020 was updated accordingly. Where a * value appears in a data set, no value is recorded on the graph or in the underlying data. This has important impacts for individuals analyzing data from small counties, where changes in small month-to-month caseloads (and the data associated with them) can be eschewed.",
    )
    
    st.caption("Where a zero appears in a data set, a zero value is recorded on the graph or underlying data.")
               
except Exception as e:
    st.error("The app crashed. Here’s the full error (so it won’t look like a blank page):")
    st.exception(e)
