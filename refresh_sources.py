from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pandas as pd

from tracker import DATA_PATH, OUTPUT_DIR, REQUIRED_COLUMNS, log_error


REFRESH_LOG_PATH = OUTPUT_DIR / "refresh_log.txt"


DATE_PATTERNS = [
    # Congress.gov and many government pages.
    ("%B %d, %Y", re.compile(r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")),
    # Some pages use ISO.
    ("%Y-%m-%d", re.compile(r"(\d{4}-\d{2}-\d{2})")),
]


STATUS_HINTS: list[tuple[str, str]] = [
    ("became public law", "Enacted"),
    ("public law no.", "Enacted"),
    ("signed by president", "Enacted"),
    ("presented to president", "Presented to President"),
    ("passed senate", "Passed Senate"),
    ("passed house", "Passed House"),
    ("agreed to in senate", "Passed Senate"),
    ("agreed to in house", "Passed House"),
    ("reported to senate", "Reported"),
    ("reported to house", "Reported"),
    ("ordered to be reported", "Reported"),
    ("committee report", "Reported"),
    ("introduced in senate", "Introduced"),
    ("introduced in house", "Introduced"),
    ("introduced", "Introduced"),
]


def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append_refresh_log(line: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with REFRESH_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")


def _safe_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _first_match_date(text: str) -> datetime | None:
    for fmt, pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(1), fmt)
        except ValueError:
            continue
    return None


def _infer_status(text: str) -> str | None:
    normalized = text.lower()
    for needle, status in STATUS_HINTS:
        if needle in normalized:
            return status
    return None


def _fetch_html(url: str, timeout_seconds: int = 25) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (LegislativeTrackerRefresh; +https://example.invalid)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="ignore")


def _normalize_ny_pdf_url(url: str) -> str:
    # Many watchlist rows point at the PDF; prefer the interactive bill page for status/actions.
    parsed = urlparse(url)
    if parsed.netloc != "legislation.nysenate.gov":
        return url
    match = re.search(r"/bills/(\d{4})/([A-Z]\d+)", parsed.path)
    if not match:
        return url
    session_year, bill_id = match.groups()
    return f"https://www.nysenate.gov/legislation/bills/{session_year}/{bill_id}"


@dataclass(frozen=True)
class RefreshResult:
    last_action_date: str | None = None
    status: str | None = None
    source_url: str | None = None


def _refresh_congress_bill(html: str) -> RefreshResult:
    # Try to locate the "Latest Action" block.
    latest_block_match = re.search(r"Latest\s+Action(.{0,2000})", html, flags=re.IGNORECASE | re.DOTALL)
    block = latest_block_match.group(1) if latest_block_match else html
    found_date = _first_match_date(block)
    if not found_date:
        return RefreshResult()

    status_hint = _infer_status(block) or _infer_status(html)
    return RefreshResult(last_action_date=found_date.strftime("%Y-%m-%d"), status=status_hint)


def _refresh_congress_report_or_event(html: str) -> RefreshResult:
    # Reports/events typically display a date near the top; best-effort date extraction.
    found_date = _first_match_date(html)
    if not found_date:
        return RefreshResult()
    return RefreshResult(last_action_date=found_date.strftime("%Y-%m-%d"))


def _refresh_nysenate_bill(html: str) -> RefreshResult:
    # The page contains an "Actions" table/list with dates. Take the most recent visible date.
    dates = []
    for _, pattern in DATE_PATTERNS:
        for match in pattern.finditer(html):
            dates.append(match.group(1))
    parsed_dates: list[datetime] = []
    for candidate in dates:
        parsed = _first_match_date(candidate)
        if parsed:
            parsed_dates.append(parsed)
    most_recent = max(parsed_dates) if parsed_dates else None

    # Try to infer a short status from common labels.
    status = None
    status_match = re.search(
        r"(IN\s+COMMITTEE|REFERRED\s+TO\s+COMMITTEE|PASSED\s+SENATE|PASSED\s+ASSEMBLY|SIGNED\s+BY\s+GOVERNOR|DELIVERED\s+TO\s+GOVERNOR)",
        html,
        flags=re.IGNORECASE,
    )
    if status_match:
        normalized = status_match.group(1).lower()
        if "signed" in normalized:
            status = "Signed by Governor"
        elif "delivered" in normalized:
            status = "Delivered to Governor"
        elif "passed senate" in normalized:
            status = "Passed Senate"
        elif "passed assembly" in normalized:
            status = "Passed Assembly"
        else:
            status = "In Committee"

    if not most_recent and not status:
        return RefreshResult()

    return RefreshResult(
        last_action_date=most_recent.strftime("%Y-%m-%d") if most_recent else None,
        status=status,
    )


def _refresh_njleg_bill(html: str) -> RefreshResult:
    # NJ legislature pages often contain an action history with dates in mm/dd/yyyy.
    mmddyyyy = re.findall(r"(\d{2}/\d{2}/\d{4})", html)
    parsed: list[datetime] = []
    for candidate in mmddyyyy:
        try:
            parsed.append(datetime.strptime(candidate, "%m/%d/%Y"))
        except ValueError:
            continue
    most_recent = max(parsed) if parsed else None

    status = None
    status_match = re.search(
        r"(Introduced|Passed\s+Senate|Passed\s+Assembly|Approved\s+by\s+the\s+Governor|Signed\s+by\s+Governor)",
        html,
        flags=re.IGNORECASE,
    )
    if status_match:
        status = status_match.group(1).title()

    if not most_recent and not status:
        return RefreshResult()
    return RefreshResult(
        last_action_date=most_recent.strftime("%Y-%m-%d") if most_recent else None,
        status=status,
    )


def _refresh_row(url: str) -> RefreshResult:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    source_url = _normalize_ny_pdf_url(url)
    html = _fetch_html(source_url)

    if netloc.endswith("congress.gov"):
        if "/bill/" in parsed.path:
            result = _refresh_congress_bill(html)
        else:
            result = _refresh_congress_report_or_event(html)
        return RefreshResult(
            last_action_date=result.last_action_date,
            status=result.status,
            source_url=source_url,
        )

    if netloc.endswith("nysenate.gov") or netloc.endswith("legislation.nysenate.gov"):
        result = _refresh_nysenate_bill(html)
        return RefreshResult(
            last_action_date=result.last_action_date,
            status=result.status,
            source_url=source_url,
        )

    if netloc.endswith("njleg.state.nj.us"):
        result = _refresh_njleg_bill(html)
        return RefreshResult(
            last_action_date=result.last_action_date,
            status=result.status,
            source_url=source_url,
        )

    return RefreshResult()


def refresh_csv(path: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    df = pd.read_csv(path, dtype=str).fillna("")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Input CSV missing required columns: {', '.join(missing)}")

    changed_status = 0
    changed_date = 0
    fetch_failures = 0

    _append_refresh_log(f"[{_now_stamp()}] Refresh started. Rows: {len(df)}")

    for idx, row in df.iterrows():
        url = _safe_text(row.get("url"))
        bill_id = _safe_text(row.get("bill_id")) or f"row-{idx+1}"
        if not url:
            continue
        normalized_url = _normalize_ny_pdf_url(url)
        if normalized_url != url:
            df.at[idx, "url"] = normalized_url
            url = normalized_url
        try:
            result = _refresh_row(url)
        except (HTTPError, URLError, TimeoutError) as exc:
            fetch_failures += 1
            msg = f"Refresh fetch failed for {bill_id} ({url}): {exc}"
            log_error(msg)
            _append_refresh_log(f"[{_now_stamp()}] {msg}")
            continue
        except Exception as exc:
            fetch_failures += 1
            msg = f"Refresh parse failed for {bill_id} ({url}): {exc}"
            log_error(msg)
            _append_refresh_log(f"[{_now_stamp()}] {msg}")
            continue

        if result.source_url and result.source_url != url:
            df.at[idx, "url"] = result.source_url

        if result.last_action_date:
            prior = _safe_text(row.get("last_action_date"))
            if prior != result.last_action_date:
                df.at[idx, "last_action_date"] = result.last_action_date
                changed_date += 1

        if result.status:
            prior_status = _safe_text(row.get("status"))
            if prior_status != result.status:
                df.at[idx, "status"] = result.status
                changed_status += 1

    _append_refresh_log(
        f"[{_now_stamp()}] Refresh completed. status_changes={changed_status} date_changes={changed_date} fetch_failures={fetch_failures}"
    )

    stats = {
        "rows": int(len(df)),
        "status_changes": changed_status,
        "date_changes": changed_date,
        "fetch_failures": fetch_failures,
    }
    return df[REQUIRED_COLUMNS].copy(), stats


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh legislative watchlist fields from official public sources.")
    parser.add_argument("--input", type=Path, default=DATA_PATH, help="Path to legislation_input.csv")
    parser.add_argument("--output", type=Path, default=DATA_PATH, help="Path to write refreshed CSV")
    parser.add_argument("--stdout", action="store_true", help="Print refreshed CSV to stdout instead of writing.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        refreshed, stats = refresh_csv(args.input)
    except Exception as exc:
        log_error(f"Refresh failed: {exc}")
        print(f"ERROR: refresh failed: {exc}", file=sys.stderr)
        return 2

    if args.stdout:
        refreshed.to_csv(sys.stdout, index=False, quoting=csv.QUOTE_MINIMAL)
    else:
        refreshed.to_csv(args.output, index=False, quoting=csv.QUOTE_MINIMAL)

    print(
        "Refresh summary: "
        + ", ".join(f"{key}={value}" for key, value in stats.items()),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
