# Legislative Tracking System

Python/Streamlit legislative intelligence dashboard for tracking active and pending federal, New York, New Jersey, and New York City legislation relevant to ports, maritime infrastructure, freight, logistics, workforce development, WRDA 2026, clean ports, and Port Authority of NY & NJ policy issues.

The current watchlist includes 36 public legislative records across federal, state, and local levels of government. It is designed as a formal policy analyst dashboard: source records live in `data/legislation_input.csv`, scoring and outputs are handled by `tracker.py`, and the Streamlit interface presents high-priority alerts, plain-language summaries, file inventory, source data, tracker logic, requirements, and generated outputs.

## Streamlit Cloud Deployment

Use this repository layout:

```text
app.py
tracker.py
requirements.txt
data/
  legislation_input.csv
outputs/
  legislative_tracker_output.xlsx
  daily_legislative_briefing.txt
  error_log.txt
refresh_sources.py
```

In Streamlit Cloud, set:

```text
Main file path: app.py
```

## Local Run

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

The app reads `data/legislation_input.csv`, regenerates the workbook and briefing in `outputs/`, and displays a last-updated timestamp.

`refresh_sources.py` provides a best-effort public-source refresh helper for supported bill pages. The dashboard itself refreshes every 12 hours when running.
