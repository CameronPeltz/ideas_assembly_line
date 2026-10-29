# House Floor Schedule to iCalendar

Small Python package that converts the U.S. House Majority Leader's weekly schedule into an `.ics` calendar. It creates one all-day event for each scheduled floor-session date and includes the publisher's meeting and vote-time wording in the event description. Session end times are not inferred.

The default source is the [official Weekly Schedule](https://www.majorityleader.gov/schedule/weekly-schedule.htm), which publishes the current week rather than an archive. `--week` selects a Monday-through-Sunday week and supplies the year omitted from its date headings. For a prior week, `--wayback` searches Internet Archive captures from the two weeks before the requested week through two weeks after it, newest first, and uses the newest capture containing schedule entries for the requested week. The search is limited to 25 captures and 90 seconds. Events generated from an archive link to that archived capture. To process a manually saved page or test offline, pass it with `--input-html`.

## Install

Install the package to make the `house-floor-schedule` command available:

```bash
python -m pip install .
```

For development, install it in editable mode with the test dependencies:

```bash
python -m pip install -e '.[test]'
```

## Usage

The simplest way to run the program is with the `house-floor-schedule` command. With no options, it fetches the official current schedule and writes `house-floor-schedule.ics` in the current directory:

```bash
house-floor-schedule
```

Use `--week` to select a week (the date must be a Monday) and `--output` to choose where to write the calendar:

```bash
house-floor-schedule --week 2026-09-14 --output /tmp/house.ics
```

Use a saved HTML page for repeatable, offline generation:

```bash
house-floor-schedule --week 2026-09-14 \
  --input-html tests/fixtures/weekly_schedule.html \
  --output /tmp/house.ics
```

Search Wayback Machine captures for a prior week:

```bash
house-floor-schedule --week 2026-08-31 --wayback --output /tmp/house.ics
```

Run `house-floor-schedule --help` to see all available options.

## Test

After installing the development dependencies, run the test suite from the project directory:

```bash
python -m pytest -q
```