# Prototype: Bill Delay Tracker

**Builds on:** [idea-bill-delay-tracker.md](../1-ideas/idea-bill-delay-tracker.md)

## What this demonstrates

Two stdlib-only Python scripts collect bill text versions from GovInfo and CRS summaries from the Congress.gov API, join them by bill and stage, and compute lag statistics; a d3 dashboard page, opened straight from disk, charts the result. The chain runs end to end on a bundled fixture without any API access.

## The fictionalized use case

The bundled fixture (`prototype-bill-delay-tracker/tests/fixture/`) is a four-row hand-made sample: two real-shaped text versions of one large bill, two introduced bills, and three summaries. It is illustrative only. Against live APIs the scripts pull real public data for the 119th Congress, but the prototype does not require that to be reviewed.

## What's in this prototype

Python 3.12, no dependencies. In [`prototype-bill-delay-tracker/`](prototype-bill-delay-tracker/):

| Script | Does |
| --- | --- |
| `collect.py` | Sweeps the GovInfo `BILLS` collection listing (one text version per row, 500 per request), fetches page counts from GovInfo package summaries and the ingest date from each version's MODS record (one call per version each, capped and cached), and sweeps `api.congress.gov/v3/summaries/{congress}/{type}` for summary versions. Incremental and resumable: every page is saved as it lands. |
| `delays.py` | Maps text versions and summaries onto four stages (introduced, reported, passed, enrolled), takes the earliest of each per bill, measures lag from the day GovInfo took the text in (`ingest.csv`; the date printed on the bill rides along as `printed_date`) to the date the API says the summary was last updated, and writes `delays.csv`, `awaiting.csv` (introduced bills with no introduced-stage summary), `stats.json` (counts, mean / median / max, per-stage stats, histograms) and `delays.json`, one record per staged text version, the dashboard's input. The same document is written again as `delays.js` (a script assigning one global) so the dashboard can load it from disk, where browsers block `fetch()` of local files. |
| `dashboard/` | The view of the data, `index.html` opened from disk or served. It measures the introduced stage only, the one CRS is summarizing in the 119th Congress and the only one where "waiting" means a queue; proposal IV.2 asks for no breakdown by stage, and the later-stage summaries CRS wrote anyway are counted in the page's caveat and kept in the data. Header metrics (the proposal's four: pages, bills summarized, bills reported by committee, mean / median / max lag), lag histogram (bin-width slider, with or without bills still waiting), bill-type and date-range filters, monthly summarized-vs-waiting shares, cumulative bills and cumulative pages (issued vs summarized), two top-10 tables, PNG / SVG / CSV exports. Hand-rolled d3 v7 (from cdnjs) in the Congressional Tech site's colors so it can move into the Astro site; pure computations in `metrics.js` under `node --test`. |
| `keys.py` | Key lookup in the same order as the Congressional Tech repo's `congress_shared.auth`: `--api-key`, `DATA_GOV_API_KEY`, `~/.data.gov.api.key`; falls back to `DEMO_KEY`. |

Real: the collectors, the join, the statistics, the dashboard. Faked: nothing, but the fixture is tiny and the live sweep is capped by default so it finishes on `DEMO_KEY`.

## How to run it

```
git clone https://github.com/CameronPeltz/ideas_assembly_line
cd ideas_assembly_line/2-prototypes/prototype-bill-delay-tracker

# 1. No API key needed: compute the bundled fixture and run the tests
python3 delays.py --data-dir tests/fixture --as-of 2026-10-14
node --test dashboard/metrics.test.mjs && python3 -m unittest discover -s tests

# 2. Live data (free key from https://api.congress.gov/sign-up/, one key covers GovInfo too)
echo YOUR_KEY > ~/.data.gov.api.key
python3 collect.py --congress 119 --max-version-pages 60 --max-page-lookups 200 --max-ingest-lookups 200 --max-summary-requests 60
python3 delays.py
# open dashboard/index.html in a browser (no server needed; or serve the folder and open /dashboard/)
```

`collect.py --help` lists the caps. Rerunning only fetches what is new.

## Live result, snapshot of 2026-10-15

`data/` in the prototype folder is a real run against the 119th Congress (collected 2026-10-15, ingest dates 2026-10-17; complete sweeps: 19,982 text versions from GovInfo, 5,337 CRS summary versions from Congress.gov, page counts and ingest dates for every version, 255,049 pages).

- 16,873 bills have text; 5,195 have at least one CRS summary; 11,989 introduced bills have no introduced-stage summary yet.
- Introduced text on GovInfo to introduced summary: n=4,779, median 85 days, mean 147.3 days, max 601 days (subject to the last-update caveat below). Measured from the printed date instead, as the first draft did, the median was 106 days: GovInfo posts an introduced bill a median 12 days after its printed date, 28 days at the 90th percentile.
- 6 introduced summaries are dated before their text reached GovInfo; the dashboard counts them and leaves them out of the histogram.
- 1,217 bills have a reported (rh/rs) text version. 511 later-stage summaries exist (337 reported, the rest passed and enrolled), the CRS exceptions; they stay in `delays.csv` and `delays.json` under their stage and the dashboard counts them in its caveat.
- Coverage by month of introduction: bills introduced in February 2025 are about 89% summarized, April 2025 40%, May 28%, and every month since about 10%. The 85-day median is the lag for the minority that got a summary at all; the monthly share chart shows the rest.

Regenerate with the two commands in "How to run it"; `collect.py` only fetches what is new.

## Known limitations

- **CRS writes summaries for introduced versions only in the 119th Congress** ("CRS is not writing bill summaries for subsequent versions of measures as they move through the legislative process", Congress.gov help, Bill Summaries, read 2026-10-16). The dashboard measures the introduced stage only and says so; `delays.py` still maps the later stages, so the exceptions CRS did write are in the CSVs and JSON for anyone who wants them.
- The Congress.gov API exposes no first-publication date for a summary, only `lastSummaryUpdateDate`, so a summary CRS revised later overstates the lag. The dashboard says so on the page. The README's "Which dates" section lists every date field both APIs offer and why these were picked; a daily collection that records when each text version and summary is first seen would replace both inferred dates with observed ones.
- The text date is the day GovInfo ingested the version (its MODS `dateIngested`, "the date the document was ingested into the GovInfo preservation repository"), days to weeks after the date printed on the bill; both are in the CSVs. GovInfo does not say an ingested package is public the same day, and the proposal's wording is publication on Congress.gov, for which the Congress.gov API has no per-version date. GovInfo's `lastModified` cannot stand in for it: a bulk reprocess in July 2026 reset it for most of the Congress.
- `DEMO_KEY` is throttled to about 30 requests per hour per IP and the Congress.gov summaries list endpoint is slow (sometimes over a minute per page), so a full-Congress sweep needs a registered key and patience.
- Page counts cover only the versions looked up so far; the dashboard says how many versions are not yet counted.
- No daily refresh job, no history, no site integration. Those are the production tool.
