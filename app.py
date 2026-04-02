import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from requests import Response

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

    HAS_AGGRID = True
except Exception:
    HAS_AGGRID = False

API_BASE = "https://clinicaltrials.gov/api/v2/studies"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000

IMPORTANT_LIMITATIONS_TEXT = """⚠️ **Technical & API Limitations**:
- No authentication required, but **rate limits apply** (unofficial but observed: stay under ~3 requests/second and ~50 requests/minute per IP to avoid temporary blocks).
- Maximum `pageSize=1000`. Fetching >10,000 studies will be slow and may hit rate limits — the app will warn before attempting large bulk fetches.
- Total studies on ClinicalTrials.gov exceed ~500,000 — you **cannot** fetch everything in real time.
- Data is **not truly real-time**: updates happen when sponsors submit records to ClinicalTrials.gov (usually daily/weekly). This dashboard shows the latest available snapshot.
- Pagination uses cursor-based tokens (not offset). New studies added mid-query can affect results.
- Some fields (dates, locations) have inconsistent formatting and may be missing.
- This app is for **exploratory/research use only**. Data is public summary information only — not for medical advice or regulatory decisions.
- Respect ClinicalTrials.gov terms of service. Do not scrape aggressively. If you need bulk data, use their official downloads instead.
- Performance note: Complex filters + large page sizes + maps can be slow on low-end devices.
"""

STATUS_OPTIONS = [
    "NOT_YET_RECRUITING",
    "RECRUITING",
    "ENROLLING_BY_INVITATION",
    "ACTIVE_NOT_RECRUITING",
    "COMPLETED",
    "SUSPENDED",
    "TERMINATED",
    "WITHDRAWN",
    "UNKNOWN",
]

PHASE_OPTIONS = [
    "EARLY_PHASE1",
    "PHASE1",
    "PHASE1_PHASE2",
    "PHASE2",
    "PHASE2_PHASE3",
    "PHASE3",
    "PHASE4",
    "NA",
]

STUDY_TYPE_OPTIONS = ["INTERVENTIONAL", "OBSERVATIONAL", "EXPANDED_ACCESS"]

DARK_MODE_CSS = """
<style>
/* App background + text */
[data-testid="stAppViewContainer"] {
  background: linear-gradient(180deg, #0b1220 0%, #0f172a 100%);
  color: #e2e8f0;
}
[data-testid="stSidebar"] {
  background: #0b1220;
}
h1, h2, h3, h4, h5, h6, p, label, div, span {
  color: #e2e8f0 !important;
}
/* Inputs */
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div, .stDateInput input {
  background-color: #111827 !important;
  color: #e5e7eb !important;
  border: 1px solid #334155 !important;
}
/* Cards / alerts */
[data-testid="stMetric"] {
  background: #111827;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 8px;
}
[data-testid="stExpander"] {
  background: #111827;
  border-radius: 10px;
}
</style>
"""

LIGHT_MODE_CSS = """
<style>
[data-testid="stAppViewContainer"] {
  background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  color: #0f172a;
}
[data-testid="stSidebar"] {
  background: #ffffff;
}
h1, h2, h3, h4, h5, h6, p, label, div, span {
  color: #0f172a !important;
}
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div, .stDateInput input {
  background-color: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #cbd5e1 !important;
}
[data-testid="stMetric"] {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 8px;
}
[data-testid="stExpander"] {
  background: #ffffff;
  border-radius: 10px;
}
</style>
"""


# -------------------------------
# Helpers
# -------------------------------

def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def parse_date_safe(date_str: Optional[str]) -> Optional[pd.Timestamp]:
    if not date_str:
        return None
    try:
        return pd.to_datetime(date_str, errors="coerce")
    except Exception:
        return None


def is_dark_theme(theme_mode: str) -> bool:
    return theme_mode == "Dark"


def plotly_theme_layout(theme_mode: str) -> Dict[str, Any]:
    dark = is_dark_theme(theme_mode)
    if dark:
        return {
            "template": "plotly_dark",
            "paper_bgcolor": "#0f172a",
            "plot_bgcolor": "#0f172a",
            "font": {"color": "#e2e8f0"},
        }
    return {
        "template": "plotly_white",
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "font": {"color": "#0f172a"},
    }


def style_altair_chart(chart: alt.Chart, theme_mode: str) -> alt.Chart:
    dark = is_dark_theme(theme_mode)
    if dark:
        return chart.configure(
            background="#0f172a"
        ).configure_axis(
            labelColor="#e2e8f0", titleColor="#e2e8f0", gridColor="#334155"
        ).configure_title(
            color="#e2e8f0"
        ).configure_view(
            strokeOpacity=0
        )
    return chart.configure(
        background="#ffffff"
    ).configure_axis(
        labelColor="#0f172a", titleColor="#0f172a", gridColor="#e2e8f0"
    ).configure_title(
        color="#0f172a"
    ).configure_view(
        strokeOpacity=0
    )


def join_list(values: Optional[List[str]], top_n: Optional[int] = None) -> str:
    if not values:
        return ""
    vals = values[:top_n] if top_n else values
    return ", ".join(v for v in vals if v)


def extract_study_fields(study: Dict[str, Any]) -> Dict[str, Any]:
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    sponsor = protocol.get("sponsorCollaboratorsModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    arms_module = protocol.get("armsInterventionsModule", {})
    contacts_locs = protocol.get("contactsLocationsModule", {})

    phases = design.get("phases", []) or []
    conditions = conditions_module.get("conditions", []) or []
    interventions = [
        i.get("name") for i in (arms_module.get("interventions", []) or []) if i.get("name")
    ]
    locations = contacts_locs.get("locations", []) or []

    return {
        "nctId": identification.get("nctId", ""),
        "briefTitle": identification.get("briefTitle", ""),
        "overallStatus": status.get("overallStatus", "UNKNOWN"),
        "phase": join_list(phases),
        "leadSponsor": (sponsor.get("leadSponsor") or {}).get("name", ""),
        "conditionsTop3": join_list(conditions, top_n=3),
        "conditions": conditions,
        "interventions": interventions,
        "locationCount": len(locations),
        "firstPostedDate": ((status.get("studyFirstPostDateStruct") or {}).get("date")),
        "lastUpdateDate": ((status.get("lastUpdatePostDateStruct") or {}).get("date")),
        "studyType": design.get("studyType", ""),
        "raw": study,
    }


def build_params(
    term: str,
    cond: str,
    intr: str,
    statuses: List[str],
    phases: List[str],
    study_types: List[str],
    sponsor_name: str,
    page_size: int,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "countTotal": "true",
        "pageSize": page_size,
    }
    if term:
        params["query.term"] = term
    if cond:
        params["query.cond"] = cond
    if intr:
        params["query.intr"] = intr
    if statuses:
        params["filter.overallStatus"] = ",".join(statuses)
    advanced_clauses = []
    if phases:
        phase_clause = " OR ".join([f"AREA[Phase]{p}" for p in phases])
        advanced_clauses.append(f"({phase_clause})")
    if study_types:
        stype_clause = " OR ".join([f"AREA[StudyType]{t}" for t in study_types])
        advanced_clauses.append(f"({stype_clause})")
    if advanced_clauses:
        params["filter.advanced"] = " AND ".join(advanced_clauses)
    if sponsor_name:
        params["query.spons"] = sponsor_name
    if page_token:
        params["pageToken"] = page_token
    return params


def api_get(params: Dict[str, Any], timeout: int = 45) -> Dict[str, Any]:
    try:
        response: Response = requests.get(API_BASE, params=params, timeout=timeout)
    except requests.exceptions.RequestException as ex:
        raise RuntimeError(f"Network error while contacting ClinicalTrials.gov API: {ex}") from ex

    if response.status_code == 429:
        raise RuntimeError(
            "Rate-limited by ClinicalTrials.gov API (HTTP 429). Wait a minute, reduce page size, or fetch fewer pages."
        )
    if response.status_code >= 500:
        raise RuntimeError(
            f"ClinicalTrials.gov API server error (HTTP {response.status_code}). Please retry shortly."
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"ClinicalTrials.gov API request failed (HTTP {response.status_code}): {response.text[:300]}"
        )

    try:
        return response.json()
    except json.JSONDecodeError as ex:
        raise RuntimeError("Failed to parse API JSON response.") from ex


def flatten_studies(studies: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = [extract_study_fields(s) for s in studies]
    if not rows:
        return pd.DataFrame(
            columns=[
                "nctId",
                "briefTitle",
                "overallStatus",
                "phase",
                "leadSponsor",
                "conditionsTop3",
                "locationCount",
                "firstPostedDate",
                "lastUpdateDate",
                "studyType",
                "conditions",
                "interventions",
                "raw",
            ]
        )
    return pd.DataFrame(rows)


def series_counter(df: pd.DataFrame, col: str, top_n: int = 10) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return pd.DataFrame({"value": [], "count": []})
    vals = []
    for entry in df[col].tolist():
        if isinstance(entry, list):
            vals.extend(entry)
        elif isinstance(entry, str) and entry:
            vals.extend([v.strip() for v in entry.split(",") if v.strip()])
    if not vals:
        return pd.DataFrame({"value": [], "count": []})
    s = pd.Series(vals).value_counts().head(top_n)
    return pd.DataFrame({"value": s.index, "count": s.values})


def fetch_single_page(params: Dict[str, Any]) -> Tuple[pd.DataFrame, int, Optional[str], Dict[str, Any]]:
    payload = api_get(params)
    studies = payload.get("studies", []) or []
    total_count = payload.get("totalCount", 0)
    next_token = payload.get("nextPageToken")
    df = flatten_studies(studies)
    return df, total_count, next_token, payload


def fetch_all_pages(base_params: Dict[str, Any], max_records: int = 20000) -> Tuple[pd.DataFrame, int]:
    all_rows = []
    page_token = None
    total_count = 0
    fetched = 0

    progress = st.progress(0, text="Starting bulk fetch...")
    while True:
        params = {**base_params}
        if page_token:
            params["pageToken"] = page_token

        payload = api_get(params)
        studies = payload.get("studies", []) or []
        total_count = payload.get("totalCount", 0)

        all_rows.extend(studies)
        fetched += len(studies)
        ratio = min(1.0, fetched / max(total_count, 1))
        progress.progress(ratio, text=f"Fetched {fetched:,} / {total_count:,} studies...")

        if fetched >= max_records:
            st.warning(f"Stopped at {max_records:,} records for safety. Narrow filters and retry if needed.")
            break

        page_token = payload.get("nextPageToken")
        if not page_token:
            break

        # Friendly throttle to respect fair use.
        time.sleep(0.4)

    progress.empty()
    return flatten_studies(all_rows), total_count


def initialize_state() -> None:
    defaults = {
        "saved_queries": [],
        "page_token": None,
        "df_current": pd.DataFrame(),
        "df_accumulated": pd.DataFrame(),
        "total_count": 0,
        "last_fetch_ts": None,
        "last_payload": {},
        "selected_nct": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def save_query_to_history(query_state: Dict[str, Any]) -> None:
    history = st.session_state.get("saved_queries", [])
    stamp = iso_now()
    entry = {"timestamp": stamp, **query_state}
    history = [entry] + [h for h in history if h != entry]
    st.session_state["saved_queries"] = history[:10]


# -------------------------------
# UI
# -------------------------------
st.set_page_config(
    page_title="ClinicalTrials.gov v2 Explorer",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialize_state()

st.title("🧪 ClinicalTrials.gov v2 Exploratory Dashboard")
st.caption("Live explorer for https://clinicaltrials.gov/api/v2/studies")

with st.sidebar:
    theme_mode = st.radio(
        "Theme mode",
        options=["Dark", "Light"],
        index=0,
        horizontal=True,
        help="Switch between dark and light dashboard themes.",
    )
    st.header("Filters")
    term = st.text_input("Free-text search (`query.term`)", help="Broad keyword search across study metadata.")
    cond = st.text_input("Condition (`query.cond`)", help="Condition-focused search query.")
    intr = st.text_input("Intervention (`query.intr`)", help="Intervention-focused search query.")
    sponsor = st.text_input("Sponsor (`query.spons`)", help="Sponsor name text filter.")

    statuses = st.multiselect(
        "Overall status (`filter.overallStatus`)",
        options=STATUS_OPTIONS,
        default=[],
        help="Select one or more trial status values.",
    )
    phases = st.multiselect(
        "Phase (mapped to `filter.advanced`)",
        options=PHASE_OPTIONS,
        default=[],
        help="Select one or more trial phases.",
    )
    study_types = st.multiselect(
        "Study type (mapped to `filter.advanced`)",
        options=STUDY_TYPE_OPTIONS,
        default=[],
        help="Optional filter for interventional/observational/expanded access.",
    )

    page_size = st.slider(
        "Page size",
        min_value=10,
        max_value=MAX_PAGE_SIZE,
        value=DEFAULT_PAGE_SIZE,
        step=10,
        help="Controls `pageSize` per API request. Large values can be slower.",
    )

    fetch_full_toggle = st.toggle(
        "Fetch full results",
        value=False,
        help="If enabled, fetches all pages for current filters using `nextPageToken`.",
    )

    st.markdown("---")
    reset = st.button("Reset all filters", use_container_width=True)

    st.markdown("---")
    with st.expander("Important Limitations & Fair-Use Notice", expanded=True):
        st.error(IMPORTANT_LIMITATIONS_TEXT)

if theme_mode == "Dark":
    st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)
else:
    st.markdown(LIGHT_MODE_CSS, unsafe_allow_html=True)

if reset:
    st.session_state.clear()
    st.rerun()

query_state = {
    "term": term,
    "cond": cond,
    "intr": intr,
    "sponsor": sponsor,
    "statuses": statuses,
    "phases": phases,
    "study_types": study_types,
    "page_size": page_size,
}
save_query_to_history(query_state)

if st.session_state.get("saved_queries"):
    with st.expander("Saved Queries (Session History)"):
        for i, q in enumerate(st.session_state["saved_queries"][:5]):
            st.caption(
                f"{i+1}. [{q['timestamp']}] term='{q.get('term','')}', cond='{q.get('cond','')}', intr='{q.get('intr','')}', statuses={q.get('statuses',[])}"
            )

base_params = build_params(
    term=term,
    cond=cond,
    intr=intr,
    statuses=statuses,
    phases=phases,
    study_types=study_types,
    sponsor_name=sponsor,
    page_size=page_size,
)

with st.spinner("Fetching live data from ClinicalTrials.gov API..."):
    try:
        if fetch_full_toggle:
            st.warning(
                "Bulk fetching may be slow and can hit rate limits. The app will stop at 20,000 records by default for safety."
            )
            df, total_count = fetch_all_pages(base_params, max_records=20000)
            st.session_state["page_token"] = None
            st.session_state["last_payload"] = {}
        else:
            df, total_count, next_page_token, payload = fetch_single_page(base_params)
            st.session_state["page_token"] = next_page_token
            st.session_state["last_payload"] = payload

        st.session_state["df_current"] = df
        st.session_state["df_accumulated"] = df.copy()
        st.session_state["total_count"] = total_count
        st.session_state["last_fetch_ts"] = iso_now()
    except RuntimeError as ex:
        st.error(str(ex))
        st.stop()

st.info(f"Last fetched: **{st.session_state['last_fetch_ts']}**")

# Summary cards
summary_df = st.session_state["df_current"]
total = st.session_state["total_count"]
status_counts = summary_df["overallStatus"].value_counts(dropna=False) if not summary_df.empty else pd.Series(dtype=int)
recruiting_pct = (status_counts.get("RECRUITING", 0) / len(summary_df) * 100) if len(summary_df) else 0
completed_pct = (status_counts.get("COMPLETED", 0) / len(summary_df) * 100) if len(summary_df) else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Matching Studies", f"{total:,}")
c2.metric("Current Loaded Rows", f"{len(summary_df):,}")
c3.metric("% Recruiting (Loaded)", f"{recruiting_pct:.1f}%")
c4.metric("% Completed (Loaded)", f"{completed_pct:.1f}%")

# Load more flow for paginated mode
if not fetch_full_toggle and st.session_state.get("page_token"):
    if st.button("Load more (next page)"):
        with st.spinner("Loading next page..."):
            try:
                more_params = {**base_params, "pageToken": st.session_state["page_token"]}
                df_more, _, next_token, _ = fetch_single_page(more_params)
                st.session_state["df_accumulated"] = pd.concat(
                    [st.session_state["df_accumulated"], df_more], ignore_index=True
                ).drop_duplicates(subset=["nctId"])
                st.session_state["df_current"] = st.session_state["df_accumulated"]
                st.session_state["page_token"] = next_token
                st.session_state["last_fetch_ts"] = iso_now()
                st.success(f"Loaded {len(df_more):,} more studies.")
            except RuntimeError as ex:
                st.error(str(ex))

render_df = st.session_state["df_current"].copy()

# Interactive table
st.subheader("Studies Table")
display_cols = [
    "nctId",
    "briefTitle",
    "overallStatus",
    "phase",
    "leadSponsor",
    "conditionsTop3",
    "locationCount",
    "firstPostedDate",
]

if HAS_AGGRID and not render_df.empty:
    # Always render a stable Streamlit dataframe so the section never appears empty.
    st.dataframe(render_df[display_cols], use_container_width=True, height=350)
    with st.expander("AgGrid view (optional)", expanded=False):
        table_df = render_df[display_cols].copy()
        gb = GridOptionsBuilder.from_dataframe(table_df)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
        gb.configure_selection("single", use_checkbox=False)
        gb.configure_default_column(filter=True, sortable=True, resizable=True)
        grid = AgGrid(
            table_df,
            gridOptions=gb.build(),
            height=350,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            fit_columns_on_grid_load=False,
        )
        selected = grid.get("selected_rows", [])
        if selected:
            selected_nct = selected[0].get("nctId")
            match = render_df[render_df["nctId"] == selected_nct]
            if not match.empty:
                raw_obj = match.iloc[0]["raw"]
                st.markdown(f"[Open on ClinicalTrials.gov](https://clinicaltrials.gov/study/{selected_nct})")
                st.json(raw_obj)
elif not render_df.empty:
    st.dataframe(render_df[display_cols], use_container_width=True, height=350)
    picked_id = st.selectbox("Select NCT ID for full JSON", [""] + render_df["nctId"].tolist())
    if picked_id:
        raw_obj = render_df[render_df["nctId"] == picked_id].iloc[0]["raw"]
        st.markdown(f"[Open on ClinicalTrials.gov](https://clinicaltrials.gov/study/{picked_id})")
        st.json(raw_obj)
else:
    st.warning("No studies found for current filters.")

# Exports
st.download_button(
    "Export current loaded rows as CSV",
    data=render_df.drop(columns=["raw"], errors="ignore").to_csv(index=False),
    file_name="clinicaltrials_current_rows.csv",
    mime="text/csv",
)

# Charts
st.subheader("Visualizations")
left, right = st.columns(2)

with left:
    if not render_df.empty:
        status_plot = render_df["overallStatus"].value_counts().reset_index()
        status_plot.columns = ["status", "count"]
        fig_status = px.pie(status_plot, names="status", values="count", title="Study Status Distribution")
        fig_status.update_layout(**plotly_theme_layout(theme_mode))
        st.plotly_chart(fig_status, use_container_width=True)

        phase_plot = series_counter(render_df, "phase", top_n=12)
        phase_chart = (
            alt.Chart(phase_plot)
            .mark_bar(color="#60a5fa" if is_dark_theme(theme_mode) else "#2563eb")
            .encode(x=alt.X("count:Q", title="Count"), y=alt.Y("value:N", sort="-x", title="Phase"), tooltip=["value", "count"])
            .properties(title="Phase Breakdown")
        )
        st.altair_chart(
            style_altair_chart(phase_chart, theme_mode),
            use_container_width=True,
        )

with right:
    sponsor_top = render_df[render_df["leadSponsor"] != ""]["leadSponsor"].value_counts().head(10).reset_index()
    sponsor_top.columns = ["sponsor", "count"]
    fig_sponsor = px.bar(sponsor_top, x="count", y="sponsor", orientation="h", title="Top 10 Sponsors", color="count", color_continuous_scale="Blues")
    fig_sponsor.update_layout(**plotly_theme_layout(theme_mode))
    st.plotly_chart(fig_sponsor, use_container_width=True)

    cond_top = series_counter(render_df, "conditions", top_n=10)
    fig_cond = px.bar(cond_top, x="count", y="value", orientation="h", title="Top 10 Conditions", color="count", color_continuous_scale="Viridis")
    fig_cond.update_layout(**plotly_theme_layout(theme_mode))
    st.plotly_chart(fig_cond, use_container_width=True)

intervention_top = series_counter(render_df, "interventions", top_n=10)
fig_intr = px.bar(intervention_top, x="count", y="value", orientation="h", title="Top 10 Interventions", color="count", color_continuous_scale="Plasma")
fig_intr.update_layout(**plotly_theme_layout(theme_mode))
st.plotly_chart(fig_intr, use_container_width=True)

# Timeline
if not render_df.empty:
    timeline = render_df.copy()
    timeline["firstPostedParsed"] = timeline["firstPostedDate"].apply(parse_date_safe)
    timeline = timeline.dropna(subset=["firstPostedParsed"])
    if not timeline.empty:
        st.plotly_chart(
            px.histogram(timeline, x="firstPostedParsed", nbins=40, title="Studies by First Posted Date").update_layout(**plotly_theme_layout(theme_mode)),
            use_container_width=True,
        )

# Geographic map (country-level aggregation for robust plotting without geocoding)
if not render_df.empty:
    country_rows = []
    for raw in render_df["raw"].tolist():
        locs = (
            raw.get("protocolSection", {})
            .get("contactsLocationsModule", {})
            .get("locations", [])
        ) or []
        for loc in locs:
            country = loc.get("country")
            city = loc.get("city")
            state = loc.get("state")
            if country:
                country_rows.append({"country": country, "city": city, "state": state})

    if country_rows:
        map_df = pd.DataFrame(country_rows)
        country_counts = map_df["country"].value_counts().reset_index()
        country_counts.columns = ["country", "count"]
        st.plotly_chart(
            px.choropleth(
                country_counts,
                locations="country",
                locationmode="country names",
                color="count",
                title="Study Locations by Country",
                color_continuous_scale="Viridis",
            ).update_layout(**plotly_theme_layout(theme_mode)),
            use_container_width=True,
        )

# Friendly sample test suggestion
st.markdown("### Quick test suggestion")
st.code("Try: condition='cancer', status=['RECRUITING'], phase=['PHASE3']")

# End-of-file API endpoint notes requested by user.
# Extra API endpoints discovered/commonly used in v2:
# - GET https://clinicaltrials.gov/api/v2/studies/{nctId}
# - GET https://clinicaltrials.gov/api/v2/studies (supports query/filter/sort/countTotal/pageToken/pageSize)
# - See official API reference pages linked from ClinicalTrials.gov for schema and enum details.
