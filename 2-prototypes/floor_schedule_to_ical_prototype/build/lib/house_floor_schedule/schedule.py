"""Read House session dates from the Majority Leader's weekly schedule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from html.parser import HTMLParser
import re


WEEKDAYS = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}
MONTHS = {
    name.upper(): number
    for number, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
        start=1,
    )
}
DATE_HEADING = re.compile(
    r"^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),\s+"
    r"(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{1,2})"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)
MEETING_STATEMENT = re.compile(
    r"\b(?:the\s+)?House\s+(?:will|is expected to|plans to)\s+(?:meet|convene)\b",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(?:not|never|no|won't|wouldn't|doesn't|isn't)\b", re.IGNORECASE)


@dataclass(frozen=True)
class FloorSession:
    """A dated House floor schedule entry, with the publisher's time wording."""

    session_date: date
    details: str


class _ScheduleText(HTMLParser):
    """Extract readable text while preserving HTML line and paragraph breaks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append("\n")
        elif tag in {"p", "div", "li"}:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li"}:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _clean_text(markup: str) -> str:
    parser = _ScheduleText()
    parser.feed(markup)
    return re.sub(r"[ \t\xa0]+", " ", "".join(parser.parts)).strip()


def _dates_for_heading(heading: re.Match[str], week_start: date, details: str) -> list[date]:
    month = MONTHS[heading.group(2).upper()]
    day = int(heading.group(3))
    week_end = week_start + timedelta(days=7)
    candidates = []
    for year in (week_start.year - 1, week_start.year, week_start.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if week_start <= candidate < week_end and candidate.weekday() == WEEKDAYS[heading.group(1).upper()]:
            candidates.append(candidate)
    if len(candidates) != 1:
        return []
    heading_date = candidates[0]

    meeting_sentences = [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", details)
        if MEETING_STATEMENT.search(sentence)
    ]
    mentioned_days: set[int] = set()
    for sentence in meeting_sentences:
        for name, weekday in WEEKDAYS.items():
            for match in re.finditer(rf"\b{name.title()}\b", sentence, re.IGNORECASE):
                context = sentence[max(0, match.start() - 40) : match.end() + 40]
                if not NEGATION.search(context):
                    mentioned_days.add(weekday)

    selected = set()
    if mentioned_days:
        selected.update(
            week_start + timedelta(days=weekday)
            for weekday in mentioned_days
            if week_start <= week_start + timedelta(days=weekday) < week_end
        )
    elif meeting_sentences:
        selected.add(heading_date)

    return sorted(selected)


def parse_weekly_schedule(markup: str, week_start: date) -> list[FloorSession]:
    """Parse schedule summaries for a Monday-through-Sunday week.

    The Majority Leader page publishes a current weekly page rather than an
    archival API. The caller supplies the requested week's Monday, which also
    supplies the year omitted from the page's date headings.
    """
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday")

    text = _clean_text(markup)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    sessions: dict[date, FloorSession] = {}
    index = 0
    while index < len(lines):
        heading = DATE_HEADING.match(lines[index])
        if not heading:
            index += 1
            continue

        summary_parts: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            if not lines[cursor]:
                cursor += 1
                continue
            if DATE_HEADING.match(lines[cursor]):
                break
            if re.match(r"^Legislation (?:Considered|that|which)|^Possible Legislation|^Additional legislative items", lines[cursor], re.IGNORECASE):
                break
            summary_parts.append(lines[cursor])
            cursor += 1
        details = " ".join(summary_parts).strip()
        if details:
            for session_date in _dates_for_heading(heading, week_start, details):
                sessions[session_date] = FloorSession(session_date, details)
        index = max(index + 1, cursor)

    return [sessions[day] for day in sorted(sessions)]