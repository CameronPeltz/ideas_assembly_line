"""Command-line interface for generating a House floor schedule calendar."""

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from house_floor_schedule.archive import WAYBACK_URL, WaybackError, fetch_wayback_schedule
from house_floor_schedule.calendar import SOURCE_URL, render_calendar
from house_floor_schedule.schedule import parse_weekly_schedule


def _monday(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.weekday() != 0:
        raise argparse.ArgumentTypeError("week must be a Monday (YYYY-MM-DD)")
    return parsed


def _read_source(input_html: Path | None) -> str:
    if input_html is not None:
        return input_html.read_text(encoding="utf-8")
    request = Request(SOURCE_URL, headers={"User-Agent": "house-floor-schedule-ical/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    today = datetime.now().date()
    default_week = today - timedelta(days=today.weekday())
    parser.add_argument("--week", type=_monday, default=default_week, help="Monday of the requested week (YYYY-MM-DD)")
    parser.add_argument("--output", type=Path, default=Path("house-floor-schedule.ics"), help="Output .ics path")
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--input-html", type=Path, help="Read saved schedule HTML instead of making a network request")
    source_group.add_argument("--wayback", action="store_true", help="Find an archived schedule for the requested week")
    args = parser.parse_args()

    capture_timestamp = None
    try:
        if args.wayback:
            archived = fetch_wayback_schedule(args.week)
            if archived is None:
                parser.error(
                    f"No Wayback Machine capture containing the week of {args.week:%Y-%m-%d} "
                    "was found in the searched date range."
                )
            markup, capture_timestamp = archived
        else:
            markup = _read_source(args.input_html)
    except WaybackError as error:
        parser.error(str(error))
    except (OSError, UnicodeError, URLError) as error:
        source = f"input file {args.input_html}" if args.input_html else SOURCE_URL
        parser.error(f"Could not read schedule from {source}: {error}")

    sessions = parse_weekly_schedule(markup, args.week)
    if not sessions:
        parser.error(
            f"No session dates found for the week of {args.week:%Y-%m-%d}. "
            "The official page shows the current week; use --input-html for a saved page "
            "or --wayback to search the Internet Archive."
        )
    archive_url = f"{WAYBACK_URL}/{capture_timestamp}/{SOURCE_URL}" if capture_timestamp else SOURCE_URL
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            render_calendar(sessions, source_url=archive_url),
            encoding="utf-8",
            newline="",
        )
    except OSError as error:
        parser.error(f"Could not write calendar to {args.output}: {error}")
    source = f" from Wayback capture {capture_timestamp}" if capture_timestamp else ""
    print(f"Wrote {len(sessions)} House floor session(s){source} to {args.output}")


if __name__ == "__main__":
    main()