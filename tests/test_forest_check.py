"""Checks for the forest loss check.

Run with:  .venv/bin/python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path

from app import database
from app.checks import fire, forest
from app.demo import load_demo_data


def square(west, south, east, north):
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


# A small square test plot, about 1.1 x 1.1 km, inside a large 2020 forest.
PLOT = square(110.00, -2.00, 110.01, -1.99)
FOREST_2020 = [square(109.95, -2.05, 110.10, -1.95)]


def check(losses, forest_2020=FOREST_2020):
    """Run the plot check with the given (geometry, year) losses."""
    forest_union, deforestation = forest.find_deforestation(forest_2020, losses)
    return forest.check_plot(PLOT, forest_union, deforestation)


class CheckPlotTests(unittest.TestCase):
    def test_clearing_on_plot_is_red(self):
        status, summary, details = check([(square(110.002, -1.998, 110.0035, -1.9965), 2023)])  # ~2.8 ha
        self.assertEqual(status, "red")
        self.assertEqual(summary, "Forest cleared on plot since 2021")
        self.assertAlmostEqual(details["cleared_ha"], 2.8, delta=0.2)
        self.assertEqual(details["cleared_years"], [2023])

    def test_tiny_clearing_on_plot_is_amber(self):
        status, _, details = check([(square(110.002, -1.998, 110.0024, -1.9975), 2023)])  # ~0.25 ha
        self.assertEqual(status, "amber")
        self.assertLess(details["cleared_ha"], 0.5)

    def test_clearing_600_m_away_is_amber(self):
        status, summary, details = check([(square(110.0155, -1.998, 110.017, -1.996), 2022)])
        self.assertEqual(status, "amber")
        self.assertEqual(summary, "Forest cleared nearby")
        self.assertAlmostEqual(details["nearest_km"], 0.6, delta=0.1)

    def test_clearing_3_km_away_is_green(self):
        status, summary, _ = check([(square(110.037, -1.998, 110.039, -1.996), 2022)])
        self.assertEqual(status, "green")
        self.assertEqual(summary, "No forest loss detected")

    def test_loss_before_2021_is_ignored(self):
        status, _, _ = check([(square(110.002, -1.998, 110.0035, -1.9965), 2019)])
        self.assertEqual(status, "green")

    def test_loss_outside_2020_forest_is_ignored(self):
        # e.g. an old plantation being replanted: not forest in 2020
        elsewhere = [square(111.0, -3.0, 111.1, -2.9)]
        status, _, details = check([(square(110.002, -1.998, 110.0035, -1.9965), 2023)], forest_2020=elsewhere)
        self.assertEqual(status, "green")
        self.assertEqual(details["forest_2020_ha"], 0)

    def test_forest_on_plot_in_2020_is_reported(self):
        _, _, details = check([])
        self.assertAlmostEqual(details["forest_2020_ha"], 123, delta=3)  # the whole plot

    def test_mill_only_is_never_green(self):
        _, deforestation = forest.find_deforestation(FOREST_2020, [(square(110.02, -1.99, 110.03, -1.98), 2023)])
        status_with, summary_with, details = forest.check_mill_only(-1.995, 110.005, deforestation)
        status_without, summary_without, _ = forest.check_mill_only(-1.995, 110.005, [])
        self.assertEqual(status_with, "amber")
        self.assertIn("forest cleared in possible sourcing area", summary_with)
        self.assertGreater(details["cleared_in_sourcing_area_ha"], 100)
        self.assertEqual(status_without, "amber")
        self.assertIn("no forest loss found", summary_without)


class DemoForestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.conn = database.connect(Path(self.temp_dir.name) / "test.db")
        load_demo_data(self.conn)
        forest.run_forest_check(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_demo_suppliers_get_expected_results(self):
        results = {s["name"]: s["checks"]["forest"]["status"] for s in database.get_suppliers(self.conn)}
        self.assertEqual(
            results,
            {
                "PT Demo Sawit Lestari": "red",
                "CV Demo Tunas Baru": "red",
                "PT Demo Agro Kapuas": "amber",
                "PT Demo Borneo Palma": "amber",
                "Koperasi Demo Tani Makmur": "green",
            },
        )

    def test_overall_plot_status_is_worst_of_both_checks(self):
        from datetime import date

        fire.run_fire_check(self.conn, today=date(2026, 10, 20))
        database.update_plot_risk_status(self.conn)
        statuses = dict(self.conn.execute("SELECT name, risk_status FROM plots"))
        self.assertEqual(statuses["Block B1"], "red")          # fire amber, forest red
        self.assertEqual(statuses["Estate block 1"], "amber")  # fire green, forest amber
        self.assertEqual(statuses["Smallholder plot 2"], "green")


if __name__ == "__main__":
    unittest.main()
