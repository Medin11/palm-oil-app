"""Checks for the fire check.

Run with:  .venv/bin/python -m unittest discover tests
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app import database
from app.checks import fire
from app.demo import load_demo_data

TODAY = date(2026, 10, 20)

# A small square test plot, about 1.1 x 1.1 km.
PLOT = {
    "type": "Polygon",
    "coordinates": [[[110.00, -2.00], [110.01, -2.00], [110.01, -1.99], [110.00, -1.99], [110.00, -2.00]]],
}


def hotspot(longitude, latitude=-1.995, detected_on="2026-09-01", confidence="nominal"):
    return {
        "latitude": latitude,
        "longitude": longitude,
        "detected_on": detected_on,
        "satellite": "VIIRS (NOAA-20)",
        "confidence": confidence,
    }


class CheckPlotTests(unittest.TestCase):
    def test_fire_inside_plot_is_red(self):
        status, summary, details = fire.check_plot(PLOT, [hotspot(110.005)])
        self.assertEqual(status, "red")
        self.assertEqual(summary, "Fire detected on plot")
        self.assertEqual(details["fires_on_plot"], 1)

    def test_fire_just_outside_plot_counts_as_on_plot(self):
        # about 330 m east of the plot edge, inside the 500 m allowance
        status, _, _ = fire.check_plot(PLOT, [hotspot(110.013)])
        self.assertEqual(status, "red")

    def test_fire_3_km_away_is_amber(self):
        status, summary, details = fire.check_plot(PLOT, [hotspot(110.037)])
        self.assertEqual(status, "amber")
        self.assertEqual(summary, "Fires detected nearby")
        self.assertAlmostEqual(details["nearest_km"], 3.0, delta=0.1)

    def test_fire_8_km_away_is_green(self):
        status, summary, details = fire.check_plot(PLOT, [hotspot(110.082)])
        self.assertEqual(status, "green")
        self.assertEqual(summary, "No fires detected nearby")
        self.assertAlmostEqual(details["nearest_km"], 8.0, delta=0.1)

    def test_no_fires_at_all_is_green(self):
        status, _, details = fire.check_plot(PLOT, [])
        self.assertEqual(status, "green")
        self.assertIsNone(details["nearest_km"])

    def test_mill_only_is_never_green(self):
        status_with, summary_with, _ = fire.check_mill_only(-1.995, 110.005, [hotspot(110.2)])
        status_without, summary_without, _ = fire.check_mill_only(-1.995, 110.005, [])
        self.assertEqual(status_with, "amber")
        self.assertIn("fires in possible sourcing area", summary_with)
        self.assertEqual(status_without, "amber")
        self.assertIn("no fires found", summary_without)


class DatabaseFireTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.conn = database.connect(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def add_hotspot(self, detected_on, confidence):
        with self.conn:
            self.conn.execute(
                "INSERT INTO fire_hotspots (latitude, longitude, detected_on, satellite, confidence) "
                "VALUES (-2, 110, ?, 'VIIRS (NOAA-20)', ?)",
                (detected_on, confidence),
            )

    def test_low_confidence_and_old_fires_are_ignored(self):
        self.add_hotspot("2026-09-01", "nominal")  # used
        self.add_hotspot("2026-09-01", "low")      # ignored: satellite unsure
        self.add_hotspot("2025-08-01", "high")     # ignored: older than 12 months
        hotspots = fire.relevant_hotspots(self.conn, today=TODAY)
        self.assertEqual(len(hotspots), 1)
        self.assertEqual(hotspots[0]["confidence"], "nominal")

    def test_demo_suppliers_get_expected_results(self):
        load_demo_data(self.conn)
        fire.run_fire_check(self.conn, today=TODAY)
        database.update_plot_risk_status(self.conn)

        results = {s["name"]: s["fire"]["status"] for s in database.get_suppliers(self.conn)}
        self.assertEqual(
            results,
            {
                "CV Demo Tunas Baru": "red",
                "PT Demo Sawit Lestari": "amber",
                "PT Demo Borneo Palma": "amber",
                "Koperasi Demo Tani Makmur": "green",
                "PT Demo Agro Kapuas": "green",
            },
        )

    def test_plot_risk_status_is_updated(self):
        load_demo_data(self.conn)
        fire.run_fire_check(self.conn, today=TODAY)
        database.update_plot_risk_status(self.conn)
        statuses = dict(self.conn.execute("SELECT name, risk_status FROM plots"))
        self.assertEqual(statuses["Plot south"], "red")
        self.assertEqual(statuses["Block B1"], "amber")
        self.assertEqual(statuses["Estate block 1"], "green")

    def test_reloading_demo_data_clears_results(self):
        load_demo_data(self.conn)
        fire.run_fire_check(self.conn, today=TODAY)
        load_demo_data(self.conn)
        count = self.conn.execute("SELECT COUNT(*) FROM check_results").fetchone()[0]
        self.assertEqual(count, 0)
        self.assertTrue(all(s["fire"] is None for s in database.get_suppliers(self.conn)))


if __name__ == "__main__":
    unittest.main()
