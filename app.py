from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from tracker import (
    BRIEFING_OUTPUT_PATH,
    DATA_PATH,
    EXCEL_OUTPUT_PATH,
    ERROR_LOG_PATH,
    DataValidationError,
    REQUIRED_COLUMNS,
    export_excel,
    generate_briefing,
    load_data,
    log_error,
    process_legislation,
)


AUTO_REFRESH_SECONDS = 12 * 60 * 60
BASE_DIR = Path(__file__).resolve().parent
REQUIREMENTS_PATH = BASE_DIR / "requirements.txt"
TRACKER_PATH = BASE_DIR / "tracker.py"
APP_PATH = BASE_DIR / "app.py"
POLICY_FOCUS = [
    "Active and pending federal, state, and local measures affecting port policy and planning",
    "Maritime, supply chain, logistics, freight rail, trucking, and transportation/distribution policy",
    "PANYNJ, New York, New Jersey, and New York City actions affecting regional port operations",
    "Harbor, cargo, working waterfront, clean port, intermodal, and workforce development issues",
]

COVERAGE_ROWS = [
    {
        "Level": "Federal",
        "Sources monitored": "Congress.gov, CRS, committee reports, appropriations and authorization measures",
        "Policy coverage": "WRDA 2026, port infrastructure grants, maritime regulation, supply chain resilience, clean ports, workforce",
    },
    {
        "Level": "New York State",
        "Sources monitored": "New York State Senate and Assembly legislation pages",
        "Policy coverage": "PANYNJ governance, capital planning, public notice, debt transparency, labor and authority oversight",
    },
    {
        "Level": "New Jersey State",
        "Sources monitored": "New Jersey Legislature bill text and status pages",
        "Policy coverage": "PANYNJ oversight, transportation authorities, logistics workforce, commercial routes, maritime facilities",
    },
    {
        "Level": "New York City",
        "Sources monitored": "NYC Council Legistar legislation records",
        "Policy coverage": "Freight rail, truck routing, last-mile facilities, blue highways, clean port operations, waterfront land use",
    },
]

FORMAL_CSS = """
<style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1500px;
    }
    h1 {
        color: #17324d;
        font-weight: 750;
        letter-spacing: 0;
    }
    h2, h3 {
        color: #17324d;
        font-weight: 700;
    }
    [data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #d9e2ec;
        border-radius: 6px;
        padding: 1rem;
    }
    [data-testid="stExpander"] {
        border: 1px solid #d9e2ec;
        border-radius: 6px;
        background: #fbfcfe;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #c9d6e2;
        border-radius: 6px;
        background: #ffffff;
    }
    .stButton a, .stDownloadButton button {
        border-radius: 4px;
        font-weight: 600;
    }
</style>
"""


st.set_page_config(
    page_title="Legislative Tracking System",
    page_icon="",
    layout="wide",
)


def _format_dates(df: pd.DataFrame) -> pd.DataFrame:
    formatted = df.copy()
    formatted["last_action_date"] = formatted["last_action_date"].dt.strftime("%Y-%m-%d")
    return formatted


def _date_label(value: object) -> str:
    date_value = pd.to_datetime(value, errors="coerce")
    if pd.isna(date_value):
        return "Unknown date"
    return date_value.strftime("%Y-%m-%d")


def _last_updated_label() -> str:
    candidates = [
        path.stat().st_mtime
        for path in (EXCEL_OUTPUT_PATH, BRIEFING_OUTPUT_PATH)
        if path.exists()
    ]
    timestamp = max(candidates) if candidates else datetime.now().timestamp()
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %I:%M %p")


@st.cache_data(show_spinner=False, ttl=AUTO_REFRESH_SECONDS)
def _load_processed_data(input_mtime: float) -> pd.DataFrame:
    raw = load_data()
    return process_legislation(raw)


def _write_outputs(df: pd.DataFrame) -> None:
    export_excel(df)
    generate_briefing(df)


def _download_button(path: Path, label: str, mime: str) -> None:
    if path.exists():
        st.download_button(
            label=label,
            data=path.read_bytes(),
            file_name=path.name,
            mime=mime,
            width="stretch",
        )
    else:
        st.info(f"{path.name} will be available after the tracker generates outputs.")


def _file_status(path: Path, label: str) -> dict[str, object]:
    exists = path.exists()
    return {
        "Item": label,
        "Path": str(path.relative_to(BASE_DIR)) if path.is_relative_to(BASE_DIR) else str(path),
        "Exists": "Yes" if exists else "No",
        "Size": f"{path.stat().st_size:,} bytes" if exists and path.is_file() else "",
        "Last modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %I:%M %p")
        if exists
        else "",
    }


def _read_text(path: Path) -> str:
    if not path.exists():
        return f"{path.name} was not found."
    return path.read_text(encoding="utf-8")


def _job_relevance_note(row: pd.Series) -> str:
    text = " ".join(
        [
            str(row.get("bill_title", "")),
            str(row.get("summary_text", "")),
            str(row.get("keywords", "")),
            str(row.get("committee", "")),
        ]
    ).lower()
    notes: list[str] = []
    if any(term in text for term in ["workforce", "career", "training", "maritime workforce"]):
        notes.append("connects to maritime and logistics career pathways")
    if any(term in text for term in ["panynj", "port authority", "new york", "new jersey"]):
        notes.append("has direct NY/NJ or Port Authority policy relevance")
    if any(term in text for term in ["cargo", "freight", "logistics", "supply chain", "shipping"]):
        notes.append("affects cargo movement, logistics, or supply chain planning")
    if any(term in text for term in ["harbor", "navigation", "wrda", "water resources", "pidp", "port infrastructure"]):
        notes.append("supports port infrastructure, harbor, or federal funding analysis")
    if any(term in text for term in ["clean ports", "zero-emission", "resilience"]):
        notes.append("relates to port modernization, resilience, or clean transportation")

    if not notes:
        return "Relevant to Port Policy & Planning research, tracking, and briefing preparation."
    return "This matters because it " + "; ".join(notes) + "."


def _render_file_inventory() -> None:
    files = [
        (APP_PATH, "Streamlit dashboard"),
        (TRACKER_PATH, "Backend tracker/scoring engine"),
        (DATA_PATH, "Input legislation CSV"),
        (EXCEL_OUTPUT_PATH, "Generated Excel workbook"),
        (BRIEFING_OUTPUT_PATH, "Generated policy briefing"),
        (ERROR_LOG_PATH, "Error log"),
        (REQUIREMENTS_PATH, "Python requirements"),
    ]
    st.dataframe(
        pd.DataFrame([_file_status(path, label) for path, label in files]),
        width="stretch",
        hide_index=True,
    )


def _render_tracker_logic() -> None:
    scoring_rules = pd.DataFrame(
        [
            {
                "Rule": "Port, maritime, freight, cargo, harbor, infrastructure, terminal, toll, bridge, tunnel, or PANYNJ keyword",
                "Score impact": "+30",
            },
            {
                "Rule": "Transportation, infrastructure funding, workforce development, federal authorization, water resources, capital plan, PIDP, clean ports, supply chain, NY/NJ signal",
                "Score impact": "+25",
            },
            {
                "Rule": "Relevant federal, NY, or NJ committee jurisdiction",
                "Score impact": "+20",
            },
            {
                "Rule": "WRDA or water infrastructure signal",
                "Score impact": "+15",
            },
            {
                "Rule": "Direct New York, New Jersey, PANYNJ, or Port Authority impact",
                "Score impact": "+15",
            },
            {
                "Rule": "Active status such as passed, reported, floor vote, enacted, or advanced",
                "Score impact": "+10",
            },
            {
                "Rule": "Stalled status or no action for more than 90 days",
                "Score impact": "-20",
            },
        ]
    )
    priority_rules = pd.DataFrame(
        [
            {"Score range": "80-100", "Priority": "HIGH PRIORITY"},
            {"Score range": "50-79", "Priority": "MEDIUM PRIORITY"},
            {"Score range": "0-49", "Priority": "LOW PRIORITY"},
        ]
    )

    left, right = st.columns([2, 1])
    with left:
        st.markdown("**Scoring Rules**")
        st.dataframe(scoring_rules, width="stretch", hide_index=True)
    with right:
        st.markdown("**Priority Labels**")
        st.dataframe(priority_rules, width="stretch", hide_index=True)

    st.markdown("**Required Input Columns**")
    st.code("\n".join(REQUIRED_COLUMNS), language="text")


def main() -> None:
    st.markdown(FORMAL_CSS, unsafe_allow_html=True)
    st.markdown(f"<meta http-equiv='refresh' content='{AUTO_REFRESH_SECONDS}'>", unsafe_allow_html=True)
    st.title("Port Policy & Planning Legislative Tracking System")
    st.caption("Port Authority of NY & NJ | Port Department | Federal, State, and Local Legislative Intelligence")

    try:
        df = _load_processed_data(DATA_PATH.stat().st_mtime)
        _write_outputs(df)
    except DataValidationError as exc:
        st.error(f"Input data validation failed. {exc}")
        return
    except FileNotFoundError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        log_error(f"Streamlit app error: {exc}")
        st.error("The tracker could not load safely. Review outputs/error_log.txt for details.")
        return

    st.caption(f"Last updated: {_last_updated_label()} | Auto-refreshes every 12 hours")

    with st.expander("Policy Focus", expanded=True):
        st.write(
            "This tracker is designed for Port Department research, briefing preparation, "
            "and policy analysis. It prioritizes active and pending public legislation "
            "from federal, New York, New Jersey, and New York City sources that may affect "
            "port operations, cargo movement, maritime infrastructure, logistics, workforce "
            "pipelines, clean ports, and regional goods movement."
        )
        st.markdown("\n".join(f"- {item}" for item in POLICY_FOCUS))

    with st.expander("Coverage Method", expanded=True):
        st.write(
            "The watchlist is built from public legislative sources and organized to capture "
            "all known active or pending measures with a plausible effect on Port Authority "
            "port policy, planning, operations, infrastructure, freight movement, and workforce "
            "development. The CSV remains the source of record, so additional public bills can "
            "be added without changing the dashboard code."
        )
        st.dataframe(pd.DataFrame(COVERAGE_ROWS), width="stretch", hide_index=True)

    st.sidebar.header("Filters")
    priorities = sorted(df["priority"].dropna().unique().tolist())
    selected_priorities = st.sidebar.multiselect(
        "Priority level",
        options=priorities,
        default=priorities,
    )

    committees = sorted(df["committee"].dropna().unique().tolist())
    selected_committees = st.sidebar.multiselect(
        "Committee",
        options=committees,
        default=committees,
    )

    statuses = sorted(df["status"].dropna().unique().tolist())
    selected_statuses = st.sidebar.multiselect(
        "Status",
        options=statuses,
        default=statuses,
    )

    min_score = st.sidebar.slider(
        "Minimum relevance score",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
    )

    filtered = df[
        df["priority"].isin(selected_priorities)
        & df["committee"].isin(selected_committees)
        & df["status"].isin(selected_statuses)
        & (df["relevance_score"] >= min_score)
    ].copy()

    total_bills, high_priority_count, avg_score = st.columns(3)
    total_bills.metric("Total bills tracked", len(filtered))
    high_priority_count.metric("High priority count", int((filtered["priority"] == "HIGH PRIORITY").sum()))
    avg_score.metric(
        "Avg relevance score",
        f"{filtered['relevance_score'].mean():.1f}" if not filtered.empty else "0.0",
    )

    alert_df = filtered[filtered["relevance_score"] >= 80].sort_values(
        by="last_action_date",
        ascending=False,
    )

    st.subheader("High Priority Alerts")
    st.caption("Each alert includes a plain-language summary and why it matters for Port Policy & Planning work.")
    if alert_df.empty:
        st.info("No bills currently meet the high priority alert threshold under the selected filters.")
    else:
        for _, row in alert_df.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['bill_id']} | {row['bill_title']}**")
                st.write(
                    f"Score {row['relevance_score']} | {row['status']} | "
                    f"{row['committee']} | Last action {_date_label(row['last_action_date'])}"
                )
                st.markdown("**Brief summary**")
                st.write(row["summary_text"])
                st.markdown("**Why it matters for Port Policy & Planning**")
                st.write(_job_relevance_note(row))
                st.link_button("Open bill source", row["url"])

    st.subheader("Full Legislative Dataset")
    search_text = st.text_input("Filter table text", placeholder="Search title, summary, committee, or keywords")
    table_df = filtered.copy()
    if search_text:
        search_space = table_df[
            ["bill_id", "bill_title", "committee", "status", "summary_text", "keywords"]
        ].astype(str).agg(" ".join, axis=1)
        table_df = table_df[search_space.str.contains(search_text, case=False, na=False)]

    st.dataframe(
        _format_dates(table_df),
        width="stretch",
        height=520,
        hide_index=True,
        column_order=[
            "priority",
            "relevance_score",
            "bill_id",
            "bill_title",
            "chamber",
            "committee",
            "status",
            "last_action_date",
            "days_since_last_action",
            "summary_text",
            "keywords",
            "url",
        ],
        column_config={
            "priority": st.column_config.TextColumn("Priority", width="medium"),
            "url": st.column_config.LinkColumn("Bill URL"),
            "relevance_score": st.column_config.ProgressColumn(
                "Relevance score",
                min_value=0,
                max_value=100,
            ),
            "summary_text": st.column_config.TextColumn("Summary", width="large"),
            "keywords": st.column_config.TextColumn("Keywords", width="medium"),
        },
    )

    briefing_col, outputs_col = st.columns([3, 2])
    with briefing_col:
        st.subheader("Generated Policy Briefing")
        st.text_area(
            "daily_legislative_briefing.txt",
            value=_read_text(BRIEFING_OUTPUT_PATH),
            height=360,
            label_visibility="collapsed",
        )
    with outputs_col:
        st.subheader("Outputs")
        _render_file_inventory()
        st.markdown("**Downloads**")
        _download_button(
            EXCEL_OUTPUT_PATH,
            "Download Excel tracker",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        _download_button(
            BRIEFING_OUTPUT_PATH,
            "Download policy briefing",
            "text/plain",
        )
        _download_button(DATA_PATH, "Download input CSV", "text/csv")

    details_tabs = st.tabs(
        [
            "Input Data",
            "Tracker Logic",
            "Requirements",
            "Source Files",
            "Error Log",
        ]
    )
    with details_tabs[0]:
        st.markdown("**Raw data/legislation_input.csv**")
        st.dataframe(load_data(), width="stretch", hide_index=True)
        st.code(_read_text(DATA_PATH), language="csv")

    with details_tabs[1]:
        _render_tracker_logic()

    with details_tabs[2]:
        st.markdown("**requirements.txt**")
        requirements = [line.strip() for line in _read_text(REQUIREMENTS_PATH).splitlines() if line.strip()]
        st.dataframe(pd.DataFrame({"Package": requirements}), width="stretch", hide_index=True)
        st.code(_read_text(REQUIREMENTS_PATH), language="text")

    with details_tabs[3]:
        st.markdown("**tracker.py**")
        st.code(_read_text(TRACKER_PATH), language="python")
        st.markdown("**app.py**")
        st.code(_read_text(APP_PATH), language="python")

    with details_tabs[4]:
        st.markdown("**outputs/error_log.txt**")
        st.text_area(
            "error_log.txt",
            value=_read_text(ERROR_LOG_PATH),
            height=240,
            label_visibility="collapsed",
        )


if __name__ == "__main__":
    main()
