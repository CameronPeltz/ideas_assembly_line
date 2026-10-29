from datetime import date, datetime, timezone
import gzip
import json
from pathlib import Path
import runpy
import subprocess
import sys
from urllib.error import URLError

import pytest

from house_floor_schedule import archive
from house_floor_schedule import cli
from house_floor_schedule.calendar import render_calendar
from house_floor_schedule.schedule import parse_weekly_schedule


FIXTURE = Path(__file__).parent / "fixtures" / "weekly_schedule.html"


def test_parse_specific_week_and_expand_balance_of_week():
    markup = FIXTURE.read_text(encoding="utf-8")

    sessions = parse_weekly_schedule(markup, date(2026, 9, 14))

    assert [session.session_date for session in sessions] == [
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
        date(2026, 9, 17),
    ]
    assert "meet at noon" in sessions[0].details
    assert "meet at 10:00 a.m." in sessions[1].details
    assert "Last votes expected no later than 3:00 p.m." in sessions[-1].details


def test_parse_schedule_with_newlines_after_html_breaks():
    markup = """\
<p><b><u>WEEK OF SEPTEMBER 14</u></b></p>
<p><b><u>MONDAY, SEPTEMBER 14<br />
</u></b>On Monday, the House will meet at noon for morning hour and 2:00 p.m. for legislative business.<br />
<br />
<b><u>Legislation Considered Under Suspension of the Rules:<br />
</u></b></p>
<p><b><u>TUESDAY, SEPTEMBER 15 AND THE BALANCE OF THE WEEK<br />
</u></b>On Tuesday, the House will meet at 10:00 a.m. for morning hour and noon for legislative business. On Wednesday and Thursday, the House will meet at 9:00 a.m. for legislative business. Last votes expected no later than 3:00 p.m.<br />
<br />
<b><u>Legislation Considered Under Suspension of the Rules:<br />
</u></b></p>
"""

    sessions = parse_weekly_schedule(markup, date(2026, 9, 14))

    assert [session.session_date for session in sessions] == [
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
        date(2026, 9, 17),
    ]


def test_does_not_add_days_that_are_not_scheduled_to_meet():
    markup = """\
<p><b>MONDAY, SEPTEMBER 14</b>
On Monday, the House will meet at noon for legislative business.
On Wednesday, the House will not meet.
The House will meet on Thursday.</p>
"""

    sessions = parse_weekly_schedule(markup, date(2026, 9, 14))

    assert [session.session_date for session in sessions] == [
        date(2026, 9, 14),
        date(2026, 9, 17),
    ]


def test_ics_has_all_day_entries_and_deterministic_uids():
    sessions = parse_weekly_schedule(FIXTURE.read_text(encoding="utf-8"), date(2026, 9, 14))
    generated_at = datetime(2026, 9, 10, tzinfo=timezone.utc)

    first = render_calendar(sessions, generated_at=generated_at)
    second = render_calendar(sessions, generated_at=generated_at)

    assert first == second
    assert "DTSTART;VALUE=DATE:20260914\r\n" in first
    assert "DTEND;VALUE=DATE:20260915\r\n" in first
    assert "SUMMARY:U.S. House floor session\r\n" in first
    assert "URL:https://www.majorityleader.gov/schedule/weekly-schedule.htm\r\n" in first


def test_calendar_links_to_supplied_archive_url():
    sessions = parse_weekly_schedule(FIXTURE.read_text(encoding="utf-8"), date(2026, 9, 14))
    archived_url = "https://web.archive.org/web/20260914080000/https://example.com/schedule"

    calendar = render_calendar(sessions, source_url=archived_url)

    assert f"URL:{archived_url}\r\n" in calendar


def test_week_must_start_on_monday():
    with pytest.raises(ValueError, match="Monday"):
        parse_weekly_schedule("", date(2026, 9, 15))


def test_week_crossing_new_year_uses_heading_year():
    sessions = parse_weekly_schedule(
        "<p><b>WEDNESDAY, JANUARY 1<br></b>On Wednesday, the House will meet at 9:00 a.m.</p>",
        date(2024, 12, 30),
    )

    assert [session.session_date for session in sessions] == [date(2025, 1, 1)]


def test_wayback_uses_newest_capture_containing_requested_week(monkeypatch):
    responses = [
        json.dumps(
            [
                ["timestamp", "original", "statuscode"],
                ["20260914080000", archive.SOURCE_URL, "200"],
                ["20260918120000", archive.SOURCE_URL, "200"],
            ]
        ).encode(),
        b"<p><b>MONDAY, AUGUST 31<br></b>On Monday, the House will meet.</p>",
        FIXTURE.read_bytes(),
    ]
    requested_urls = []

    class Response:
        def __init__(self, content):
            self.content = content
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return self.content

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return Response(responses.pop(0))

    monkeypatch.setattr(archive, "urlopen", fake_urlopen)

    result = archive.fetch_wayback_schedule(date(2026, 9, 14))

    assert result is not None
    markup, timestamp = result
    assert timestamp == "20260914080000"
    assert parse_weekly_schedule(markup, date(2026, 9, 14))
    assert "/20260918120000id_/" in requested_urls[1]
    assert "/20260914080000id_/" in requested_urls[2]
    assert "from=20260831" in requested_urls[0]
    assert "to=20261004" in requested_urls[0]


def test_wayback_returns_none_when_no_capture_contains_requested_week(monkeypatch):
    responses = [
        json.dumps(
            [
                ["timestamp", "original", "statuscode"],
                ["20260914080000", archive.SOURCE_URL, "200"],
            ]
        ).encode(),
        b"<p><b>MONDAY, AUGUST 31<br></b>On Monday, the House will meet.</p>",
    ]

    class Response:
        def __init__(self, content):
            self.content = content
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return self.content

    monkeypatch.setattr(archive, "urlopen", lambda request, timeout: Response(responses.pop(0)))

    assert archive.fetch_wayback_schedule(date(2026, 9, 14)) is None


def test_wayback_empty_cdx_response_means_no_captures(monkeypatch):
    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return b"[]"

    monkeypatch.setattr(archive, "urlopen", lambda request, timeout: Response())

    assert archive.fetch_wayback_schedule(date(2026, 9, 14)) is None


def test_wayback_reports_capture_retrieval_errors(monkeypatch):
    cdx_response = json.dumps(
        [
            ["timestamp", "original", "statuscode"],
            ["20260908131423", archive.SOURCE_URL, "200"],
        ]
    ).encode()

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return cdx_response

    requests = 0

    def fake_urlopen(request, timeout):
        nonlocal requests
        requests += 1
        if requests == 1:
            return Response()
        raise URLError("connection refused")

    monkeypatch.setattr(archive, "urlopen", fake_urlopen)

    with pytest.raises(archive.WaybackError, match="Could not check all archived"):
        archive.fetch_wayback_schedule(date(2026, 8, 31))


def test_wayback_finds_capture_after_requested_week(monkeypatch):
    archived_markup = """\
<p><b><u>WEEK OF AUGUST 31</u></b></p>
<p><b><u>MONDAY, AUGUST 31<br />
</u></b>On Monday, the House will meet at noon for legislative business.</p>
"""
    responses = [
        json.dumps(
            [
                ["timestamp", "original", "statuscode"],
                ["20260908131423", archive.SOURCE_URL, "200"],
            ]
        ).encode(),
        archived_markup.encode(),
    ]

    class Response:
        def __init__(self, content):
            self.content = content
            self.headers = {"Content-Encoding": "gzip"} if content.startswith(b"<p>") else {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return gzip.compress(self.content) if self.headers else self.content

    monkeypatch.setattr(archive, "urlopen", lambda request, timeout: Response(responses.pop(0)))

    result = archive.fetch_wayback_schedule(date(2026, 8, 31))

    assert result == (archived_markup, "20260908131423")


def test_wayback_reports_when_capture_limit_prevents_full_search(monkeypatch):
    cdx_response = json.dumps(
        [
            ["timestamp", "original", "statuscode"],
            ["20260908131423", archive.SOURCE_URL, "200"],
            ["20260907131423", archive.SOURCE_URL, "200"],
        ]
    ).encode()
    responses = [cdx_response, b"<p>No schedule dates here.</p>"]

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return responses.pop(0)

    monkeypatch.setattr(archive, "MAX_WAYBACK_CAPTURES", 1)
    monkeypatch.setattr(archive, "urlopen", lambda request, timeout: Response())

    with pytest.raises(archive.WaybackError, match="limited to the 1 newest captures"):
        archive.fetch_wayback_schedule(date(2026, 8, 31))


def test_cli_reports_missing_input_file_without_traceback(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        ["house-floor-schedule", "--week", "2026-09-14", "--input-html", str(tmp_path / "missing.html")],
    )

    with pytest.raises(SystemExit, match="2"):
        cli.main()

    assert "Could not read schedule from input file" in capsys.readouterr().err


def test_module_entry_point_displays_cli_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["house_floor_schedule", "--help"])

    with pytest.raises(SystemExit) as error:
        runpy.run_module("house_floor_schedule", run_name="__main__")

    assert error.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_package_directory_entry_point_displays_cli_help():
    package_directory = Path(__file__).parents[1] / "src" / "house_floor_schedule"
    result = subprocess.run(
        [sys.executable, str(package_directory), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_cli_reports_output_write_error_without_traceback(monkeypatch, capsys, tmp_path):
    source = tmp_path / "schedule.html"
    source.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    output_parent = tmp_path / "not-a-directory"
    output_parent.write_text("file", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "house-floor-schedule",
            "--week",
            "2026-09-14",
            "--input-html",
            str(source),
            "--output",
            str(output_parent / "schedule.ics"),
        ],
    )

    with pytest.raises(SystemExit, match="2"):
        cli.main()

    assert "Could not write calendar to" in capsys.readouterr().err