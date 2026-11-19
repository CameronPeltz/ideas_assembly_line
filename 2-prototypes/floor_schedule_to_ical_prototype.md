# Prototype: Floor Schedule to iCal

**Builds on:** [floor_schedule_to_ical_idea.md](../1-ideas/floor_schedule_to_ical_idea.md)

## What's in this prototype

This is currently just a working prototype for "Floor Schedule to iCal & Enhanced Congressional Schedule Aggregation." It's a Python package that emits one .ics file for the House weekly floor schedule, pulling from the Majority Leader's website for the weekly schedule of the House of Representatives.

https://congressional-tech-backlog.netlify.app/#pII.4

As far as the developer can tell, the main source for the House of Representatives weekly schedule is here: https://www.majorityleader.gov/schedule/weekly-schedule.htm

This program also provides a way to use the Wayback Machine to search for internet archive captures. It seemed like a good idea to test more than just the current version of the website because otherwise we would be testing with only one week. The House was not in legislative session at the time of programming, so the Majority Leader website would not be updated for a few weeks.

## How to run it

Please see the README for more detailed instructions: [README.md](floor_schedule_to_ical_prototype/README.md)

Install the package to make the `house-floor-schedule` command available:

```bash
python -m pip install .
```

The simplest way to run the program is with the `house-floor-schedule` command. With no options, it fetches the official current schedule and writes `house-floor-schedule.ics` in the current directory:

```bash
house-floor-schedule
```

Use `--week` to select a week (the date must be a Monday) and `--output` to choose where to write the calendar:

```bash
house-floor-schedule --week 2026-09-14 --output /tmp/house.ics
```

## Known limitations or potential issues

Is there a better source to pull the House weekly schedule from than this site?: https://www.majorityleader.gov/schedule/weekly-schedule.htm

The weekly schedule does not list end times for any sessions, so currently there are just all-day events on the iCal. Not sure if this is the best method.

This program does not currently pull in any Senate schedules. There does not appear to be a single simple website for the weekly Senate schedule (as far as the developer is aware).
