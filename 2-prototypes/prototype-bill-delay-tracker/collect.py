#!/usr/bin/env python3
"""Collect bill text versions (GovInfo) and CRS summaries (Congress.gov) for one Congress.

Writes, under --data-dir (default ./data):
  versions.csv   one row per bill text version  (GovInfo BILLS collection listing)
  pages.csv      page count per text version    (GovInfo package summary, one call each)
  summaries.csv  one row per CRS summary version (Congress.gov /summaries list)

Every collector is incremental and resumable: rows already on disk are kept and
only new ones are fetched. Stdlib only. DEMO_KEY works but is slow and capped
(~30 requests/hour), so the --max-* knobs default low; raise them with a real key.
"""
import argparse
import concurrent.futures
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from keys import load_key

GOVINFO = "https://api.govinfo.gov"
CONGRESS = "https://api.congress.gov/v3"
BILL_TYPES = ["hr", "s", "hjres", "sjres"]
UA = "bill-delay-tracker prototype (civic tech dc)"


def get_json(url, key, timeout=90, retries=3):
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}api_key={key}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1)
                print(f"  429 rate limited, sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  retry {attempt + 1}/{retries} after {e}", file=sys.stderr)
            time.sleep(5)
    print(f"  gave up on {url}", file=sys.stderr)
    return None


def get_text(url, key, timeout=90, retries=3):
    """Like get_json for a text or XML body (GovInfo MODS)."""
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}api_key={key}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1)
                print(f"  429 rate limited, sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  retry {attempt + 1}/{retries} after {e}", file=sys.stderr)
            time.sleep(5)
    print(f"  gave up on {url}", file=sys.stderr)
    return None


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def parse_package_id(pid):
    """BILLS-119hr10786ih -> ('119','hr','10786','ih')."""
    body = pid.split("-", 1)[1]
    congress = body[:3]
    rest = body[3:]
    i = 0
    while i < len(rest) and rest[i].isalpha():
        i += 1
    bill_type = rest[:i]
    j = i
    while j < len(rest) and rest[j].isdigit():
        j += 1
    return congress, bill_type, rest[i:j], rest[j:]


VERSION_FIELDS = ["package_id", "congress", "bill_type", "number", "version", "date_issued", "last_modified", "title"]


def collect_versions(data_dir, key, congress, since, max_requests):
    path = data_dir / "versions.csv"
    rows = read_csv(path)
    seen = {r["package_id"] for r in rows}
    url = (f"{GOVINFO}/collections/BILLS/{since}T00:00:00Z?offsetMark=*&pageSize=500"
           f"&congress={congress}")
    n = 0
    while url and n < max_requests:
        n += 1
        page = get_json(url, key, timeout=120)
        if page is None:
            break
        pkgs = page.get("packages", [])
        new = 0
        for p in pkgs:
            pid = p["packageId"]
            if pid in seen:
                continue
            c, bt, num, ver = parse_package_id(pid)
            if bt not in BILL_TYPES:
                continue
            rows.append({"package_id": pid, "congress": c, "bill_type": bt, "number": num, "version": ver,
                         "date_issued": p.get("dateIssued", ""), "last_modified": p.get("lastModified", ""),
                         "title": p.get("title", "")})
            seen.add(pid)
            new += 1
        print(f"versions: page {n}, {len(pkgs)} packages, {new} new (total {len(rows)})", file=sys.stderr)
        write_csv(path, rows, VERSION_FIELDS)
        url = page.get("nextPage")
        if url and "api_key=" in url:
            url = url.split("api_key=")[0].rstrip("&?")
    return rows


def collect_pages(data_dir, key, versions, max_requests):
    path = data_dir / "pages.csv"
    rows = read_csv(path)
    have = {r["package_id"] for r in rows}
    todo = [v for v in versions if v["package_id"] not in have]
    # newest first so a capped run covers the live end of the Congress
    todo.sort(key=lambda v: v["date_issued"], reverse=True)
    for v in todo[:max_requests]:
        s = get_json(f"{GOVINFO}/packages/{v['package_id']}/summary", key)
        pages = (s or {}).get("pages", "")
        rows.append({"package_id": v["package_id"], "pages": pages})
        write_csv(path, rows, ["package_id", "pages"])
    print(f"pages: {min(len(todo), max_requests)} fetched, {len(todo) - min(len(todo), max_requests)} still missing",
          file=sys.stderr)
    write_csv(path, rows, ["package_id", "pages"])
    return rows


INGEST_FIELDS = ["package_id", "date_ingested"]


def collect_ingest(data_dir, key, versions, max_requests, workers=4):
    """GovInfo's dateIssued is the date printed on the bill (for an introduced bill, the day it was
    introduced), not the day the text appeared on GovInfo. The MODS record carries dateIngested, the
    day GovInfo took the package in, and that is the publication date the lag should start from.
    One MODS call per version, newest first, written to ingest.csv as it lands; resumable."""
    path = data_dir / "ingest.csv"
    rows = read_csv(path)
    have = {r["package_id"] for r in rows}
    todo = [v for v in versions if v["package_id"] not in have]
    todo.sort(key=lambda v: v["date_issued"], reverse=True)
    todo = todo[:max_requests]

    def fetch(v):
        x = get_text(f"{GOVINFO}/packages/{v['package_id']}/mods", key)
        m = re.search(r"<dateIngested[^>]*>([^<]+)</dateIngested>", x or "")
        return {"package_id": v["package_id"], "date_ingested": m.group(1).strip()[:10] if m else ""}

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(fetch, todo):
            rows.append(row)
            done += 1
            if done % 200 == 0 or done == len(todo):
                write_csv(path, rows, INGEST_FIELDS)
                print(f"ingest: {done}/{len(todo)} fetched, {sum(1 for r in rows if not r['date_ingested'])} without a date",
                      file=sys.stderr)
    write_csv(path, rows, INGEST_FIELDS)
    print(f"ingest: {len(todo)} fetched, {len(versions) - len(rows)} still missing", file=sys.stderr)
    return rows


SUMMARY_FIELDS = ["congress", "bill_type", "number", "version_code", "action_desc", "action_date",
                  "update_date", "current_chapter", "last_summary_update_date"]


def collect_summaries(data_dir, key, congress, since, max_requests, page_size):
    """Sweep /summaries/{congress}/{type} newest-first. Resumable: rows on disk are a
    newest-first prefix of the API's list, so after re-reading the first page (which
    catches summaries added since) a page with nothing new jumps to the end of the prefix."""
    path = data_dir / "summaries.csv"
    rows = read_csv(path)
    seen = {(r["bill_type"], r["number"], r["version_code"]) for r in rows}
    n = 0
    for bt in BILL_TYPES:
        offset = 0
        known = sum(1 for r in rows if r["bill_type"] == bt)
        while n < max_requests:
            n += 1
            q = urllib.parse.urlencode({"format": "json", "limit": page_size, "offset": offset,
                                        "sort": "updateDate desc", "fromDateTime": f"{since}T00:00:00Z"})
            page = get_json(f"{CONGRESS}/summaries/{congress}/{bt}?{q}", key, timeout=120, retries=2)
            if page is None:
                break
            items = page.get("summaries", [])
            new = 0
            for s in items:
                b = s.get("bill", {})
                k = (b.get("type", "").lower(), str(b.get("number", "")), s.get("versionCode", ""))
                if k in seen:
                    continue
                rows.append({"congress": str(b.get("congress", congress)), "bill_type": k[0], "number": k[1],
                             "version_code": k[2], "action_desc": s.get("actionDesc", ""),
                             "action_date": s.get("actionDate", ""), "update_date": s.get("updateDate", ""),
                             "current_chapter": s.get("currentChapter", ""),
                             "last_summary_update_date": s.get("lastSummaryUpdateDate", "")})
                seen.add(k)
                new += 1
            total = (page or {}).get("pagination", {}).get("count", "?")
            print(f"summaries/{bt}: offset {offset}, {len(items)} items, {new} new, api total {total}", file=sys.stderr)
            write_csv(path, rows, SUMMARY_FIELDS)
            known += new
            if len(items) < page_size:
                break
            offset = known if new == 0 and known > offset + page_size else offset + page_size
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--congress", default="119")
    ap.add_argument("--since", default="2025-01-03", help="earliest lastModified / updateDate to sweep")
    ap.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "data")
    ap.add_argument("--api-key")
    ap.add_argument("--max-version-pages", type=int, default=3, help="GovInfo listing pages of 500")
    ap.add_argument("--max-page-lookups", type=int, default=20, help="GovInfo per-version page-count calls")
    ap.add_argument("--max-ingest-lookups", type=int, default=20, help="GovInfo per-version MODS calls (dateIngested)")
    ap.add_argument("--max-summary-requests", type=int, default=4, help="Congress.gov summary list pages")
    ap.add_argument("--summary-page-size", type=int, default=250)
    ap.add_argument("--skip", nargs="*", default=[], choices=["versions", "pages", "ingest", "summaries"])
    a = ap.parse_args()
    key = load_key(a.api_key)
    print(f"key: {'DEMO_KEY (slow, capped)' if key == 'DEMO_KEY' else 'real key'}", file=sys.stderr)
    a.data_dir.mkdir(parents=True, exist_ok=True)
    versions = read_csv(a.data_dir / "versions.csv")
    if "versions" not in a.skip:
        versions = collect_versions(a.data_dir, key, a.congress, a.since, a.max_version_pages)
    if "pages" not in a.skip:
        collect_pages(a.data_dir, key, versions, a.max_page_lookups)
    if "ingest" not in a.skip:
        collect_ingest(a.data_dir, key, versions, a.max_ingest_lookups)
    if "summaries" not in a.skip:
        collect_summaries(a.data_dir, key, a.congress, a.since, a.max_summary_requests, a.summary_page_size)


if __name__ == "__main__":
    main()
