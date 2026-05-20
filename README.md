# Legislative Tracking System

Python/Streamlit legislative intelligence dashboard for tracking federal, New York, and New Jersey legislation relevant to ports, maritime infrastructure, freight, workforce development, WRDA 2026, and Port Authority of NY & NJ policy issues.

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
