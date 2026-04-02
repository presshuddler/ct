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

## Run in your browser directly from GitHub (no local install)

### Option 1 (Recommended): Streamlit Community Cloud

This is the easiest way to run the dashboard in a browser from a GitHub repo.

1. Push this repository to GitHub (it already includes `app.py` + `requirements.txt`).
2. Go to https://share.streamlit.io/
3. Click **New app** and connect/select your GitHub repository.
4. Set:
   - **Branch**: your desired branch (e.g., `main`)
   - **Main file path**: `app.py`
5. Click **Deploy**.

After deployment, Streamlit gives you a public URL you can open in any browser.

### Option 2: GitHub Codespaces (browser IDE + terminal)

If you prefer to run it yourself in a browser-hosted dev environment:

1. Open the repo on GitHub.
2. Click **Code** → **Codespaces** → **Create codespace on [branch]**.
3. In the Codespaces terminal, run:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py --server.port 8501 --server.address 0.0.0.0
   ```
4. Open the forwarded port URL that Codespaces shows.

> Note: Codespaces still installs dependencies, but everything happens in the cloud (nothing local on your machine).

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
