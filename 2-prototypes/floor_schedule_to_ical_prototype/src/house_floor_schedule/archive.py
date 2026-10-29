"""Retrieve historical House floor schedules from the Wayback Machine."""

from __future__ import annotations

from datetime import date, timedelta
import gzip
import json
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from house_floor_schedule.calendar import SOURCE_URL
from house_floor_schedule.schedule import parse_weekly_schedule


CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_URL = "https://web.archive.org/web"
USER_AGENT = "house-floor-schedule-ical/0.1"
MAX_WAYBACK_CAPTURES = 25
WAYBACK_TOTAL_TIMEOUT = 90.0
WAYBACK_REQUEST_TIMEOUT = 15.0


class WaybackError(RuntimeError):
    """Raised when the Wayback Machine cannot provide archive results."""


def fetch_wayback_schedule(week_start: date) -> tuple[str, str] | None:
    """Return the newest archived HTML containing the requested week, if any."""
    deadline = time.monotonic() + WAYBACK_TOTAL_TIMEOUT
    week_end = week_start + timedelta(days=6)
    params = urlencode(
        {
            "url": SOURCE_URL,
            "output": "json",
            "filter": "statuscode:200",
            "from": (week_start - timedelta(days=14)).strftime("%Y%m%d"),
            "to": (week_end + timedelta(days=14)).strftime("%Y%m%d"),
            "fl": "timestamp,original,statuscode",
        }
    )
    request = Request(
        f"{CDX_URL}?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=min(30.0, max(0.1, deadline - time.monotonic()))) as response:
            records = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError) as error:
        raise WaybackError(f"Could not query the Wayback Machine CDX index: {error}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise WaybackError("The Wayback Machine returned invalid CDX JSON.") from error

    if not isinstance(records, list):
        raise WaybackError("The Wayback Machine returned an invalid CDX response.")
    if not records:
        return None

    header = records[0]
    if not isinstance(header, list) or not {"timestamp", "original", "statuscode"}.issubset(header):
        raise WaybackError("The Wayback Machine CDX response is missing expected fields.")
    positions = {name: header.index(name) for name in ("timestamp", "original", "statuscode")}

    captures: list[str] = []
    for record in records[1:]:
        if not isinstance(record, list) or len(record) <= max(positions.values()):
            continue
        timestamp = record[positions["timestamp"]]
        original = record[positions["original"]]
        status = record[positions["statuscode"]]
        if (
            isinstance(timestamp, str)
            and timestamp.isdigit()
            and original == SOURCE_URL
            and status == "200"
        ):
            captures.append(timestamp)

    captures.sort(reverse=True)
    search_limited = len(captures) > MAX_WAYBACK_CAPTURES
    captures = captures[:MAX_WAYBACK_CAPTURES]
    replay_errors: list[str] = []
    timed_out = False
    for timestamp in captures:
        replay_url = f"{WAYBACK_URL}/{timestamp}id_/{SOURCE_URL}"
        replay_request = Request(replay_url, headers={"User-Agent": USER_AGENT})
        for attempt in range(2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                with urlopen(
                    replay_request,
                    timeout=min(WAYBACK_REQUEST_TIMEOUT, remaining),
                ) as response:
                    content = response.read()
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        content = gzip.decompress(content)
                    markup = content.decode("utf-8", errors="replace")
                break
            except (URLError, TimeoutError, OSError) as error:
                if attempt == 1:
                    replay_errors.append(f"{timestamp}: {error}")
        else:
            continue
        if timed_out:
            break
        if parse_weekly_schedule(markup, week_start):
            return markup, timestamp

    if timed_out:
        raise WaybackError(
            f"Wayback search exceeded its {WAYBACK_TOTAL_TIMEOUT:g}-second time limit."
        )
    if replay_errors:
        failures = "; ".join(replay_errors)
        raise WaybackError(
            "Could not check all archived schedule pages, so no matching capture "
            f"could be confirmed: {failures}"
        )
    if search_limited:
        raise WaybackError(
            f"Wayback search was limited to the {MAX_WAYBACK_CAPTURES} newest captures; "
            "no matching schedule was found among them."
        )
    return None
