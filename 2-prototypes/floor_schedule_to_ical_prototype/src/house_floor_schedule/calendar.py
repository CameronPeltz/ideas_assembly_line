"""Serialize House floor schedule entries as RFC 5545 iCalendar."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

from house_floor_schedule.schedule import FloorSession


SOURCE_URL = "https://www.majorityleader.gov/schedule/weekly-schedule.htm"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def _fold(line: str) -> str:
    """Fold content lines at 75 UTF-8 octets as required by RFC 5545."""
    chunks: list[str] = []
    current = ""
    width = 0
    for character in line:
        encoded_width = len(character.encode("utf-8"))
        if width + encoded_width > 75:
            chunks.append(current)
            current = " "
            width = 1
        current += character
        width += encoded_width
    chunks.append(current)
    return "\r\n".join(chunks)


def render_calendar(
    sessions: list[FloorSession],
    *,
    generated_at: datetime | None = None,
    source_url: str = SOURCE_URL,
) -> str:
    """Return a stable VCALENDAR document for the supplied sessions."""
    timestamp = generated_at or datetime.now(timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Civic Tech DC//House Floor Schedule//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:U.S. House Floor Schedule",
    ]
    for session in sessions:
        start = session.session_date
        uid = sha256(f"house-floor:{start.isoformat()}".encode()).hexdigest() + "@house-floor-schedule"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{timestamp}",
                f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                f"DTEND;VALUE=DATE:{start + timedelta(days=1):%Y%m%d}",
                f"SUMMARY:{_escape('U.S. House floor session')}",
                f"DESCRIPTION:{_escape(session.details)}",
                f"URL:{_escape(source_url)}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"