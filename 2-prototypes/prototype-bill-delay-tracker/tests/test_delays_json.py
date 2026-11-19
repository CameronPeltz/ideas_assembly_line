import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTO = HERE.parent


class DelaysJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        for name in ("versions.csv", "pages.csv", "summaries.csv", "ingest.csv"):
            shutil.copy(HERE / "fixture" / name, cls.tmp / name)
        subprocess.run([sys.executable, str(PROTO / "delays.py"), "--data-dir", str(cls.tmp),
                        "--as-of", "2026-10-14"], check=True, capture_output=True)
        cls.doc = json.loads((cls.tmp / "delays.json").read_text())
        cls.records = cls.doc["records"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_envelope(self):
        self.assertEqual(self.doc["as_of"], "2026-10-14")
        self.assertEqual(self.doc["congress"], "119")

    def test_one_record_per_version(self):
        # fixture: hr1 rh + eh + eah (later passed-stage edition), hr10786 ih, hr10779 ih, plus one unmapped rfs edition of hr1
        self.assertEqual(len(self.records), 6)
        keys = sorted((r["type"], r["number"], r["stage"] or "-") for r in self.records)
        self.assertEqual(keys, [("hr", "1", "-"), ("hr", "1", "-"), ("hr", "1", "passed"), ("hr", "1", "reported"),
                                ("hr", "10779", "introduced"), ("hr", "10786", "introduced")])

    def test_later_edition_of_a_staged_stage_has_no_stage(self):
        r = next(r for r in self.records if r["printed_date"] == "2025-07-02")
        self.assertEqual(r["text_date"], "2025-07-03")  # GovInfo ingest date, not the printed date
        self.assertIsNone(r["stage"])
        self.assertIsNone(r["lag_days"])
        self.assertEqual(sum(1 for r in self.records if r["stage"] == "passed"), 1)

    def test_unmapped_version_keeps_pages_and_has_no_stage(self):
        r = next(r for r in self.records if r["stage"] is None and r["printed_date"] == "2025-05-23")
        self.assertEqual(r["text_date"], "2025-05-27")
        self.assertEqual(r["pages"], 900)
        self.assertIsNone(r["lag_days"])

    def test_summary_before_text_counted(self):
        # fixture summaries.csv has an Introduced summary for hr 99999, which has no text version
        self.assertEqual(self.doc["summary_before_text"], {"introduced": 1})

    def test_summarized_record(self):
        r = next(r for r in self.records if r["number"] == "1" and r["stage"] == "reported")
        self.assertEqual(r["printed_date"], "2025-05-20")  # the date printed on the bill
        self.assertEqual(r["text_date"], "2025-05-21")  # the day GovInfo took the text in (ingest.csv)
        self.assertEqual(r["summary_date"], "2025-09-22")
        self.assertEqual(r["lag_days"], 124)
        self.assertEqual(r["pages"], 1118)
        self.assertTrue(r["reported"])
        self.assertEqual(r["title"], "One Big Beautiful Bill Act")

    def test_summary_date_is_last_summary_update_not_record_update(self):
        # fixture: hr1 Passed House has updateDate 2025-06-16 and lastSummaryUpdateDate 2025-06-10
        r = next(r for r in self.records if r["number"] == "1" and r["stage"] == "passed")
        self.assertEqual(r["summary_date"], "2025-06-10")
        self.assertEqual(r["lag_days"], 18)  # from the eh ingest date 2025-05-23

    def test_envelope_counts_versions_without_ingest_date(self):
        self.assertEqual(self.doc["versions_without_ingest_date"], 0)

    def test_waiting_record_has_nulls(self):
        r = next(r for r in self.records if r["number"] == "10779")
        self.assertIsNone(r["summary_date"])
        self.assertIsNone(r["lag_days"])
        self.assertIsNone(r["pages"])
        self.assertFalse(r["reported"])

    def test_count_matches_csvs(self):
        import csv
        with (self.tmp / "delays.csv").open(newline="") as f:
            delays = list(csv.DictReader(f))
        with (self.tmp / "awaiting.csv").open(newline="") as f:
            awaiting = list(csv.DictReader(f))
        waiting = [r for r in self.records if r["lag_days"] is None]
        self.assertEqual(len([r for r in self.records if r["lag_days"] is not None]), len(delays))
        # awaiting.csv only lists the introduced stage; the json lists waiting at every stage
        self.assertGreaterEqual(len(waiting), len(awaiting))


if __name__ == "__main__":
    unittest.main()
