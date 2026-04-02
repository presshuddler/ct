# ClinicalTrials.gov v2 Exploratory Dashboard (Streamlit)

Interactive exploratory dashboard for the ClinicalTrials.gov v2 Data API:
- Endpoint: `https://clinicaltrials.gov/api/v2/studies`
- Live filtering with API requests on each change
- Summary cards, interactive table, chart suite, map, timeline, CSV export
- Cursor pagination (`nextPageToken`) and bulk fetching workflow

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL shown by Streamlit (usually `http://localhost:8501`).

## Recommended manual test

Use filters:
- Condition: `cancer`
- Status: `RECRUITING`
- Phase: `PHASE3`

## Notes

- This app performs **live API calls** (minimal caching by design).
- Bulk fetch mode is intentionally guarded and throttled to reduce rate-limit risk.
- Saved query history is currently session-scoped (resets on browser/app restart).

## Install dependencies individually

```bash
pip install streamlit pandas plotly folium streamlit-aggrid requests altair
```

(Plotly map is used by default; `folium` is optional.)
