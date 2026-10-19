"""Checks for the database and the example data.

Run with:  .venv/bin/python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path

from app import database
from app.api import Api


class ExampleDataTests(unittest.TestCase):
    def setUp(self):
        # Use a throwaway database so the tests never touch the real one.
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.api = Api(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_loads_five_suppliers(self):
        result = self.api.load_example_data()
        self.assertEqual(result["suppliers_loaded"], 5)
        self.assertEqual(len(self.api.get_suppliers()), 5)

    def test_loading_twice_does_not_duplicate(self):
        self.api.load_example_data()
        self.api.load_example_data()
        self.assertEqual(len(self.api.get_suppliers()), 5)

        conn = database.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM mills").fetchone()[0], 5)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM plots").fetchone()[0], 8)
        conn.close()

    def test_one_supplier_has_mill_only(self):
        self.api.load_example_data()
        without_plots = [s for s in self.api.get_suppliers() if s["plot_count"] == 0]
        self.assertEqual(len(without_plots), 1)
        self.assertIsNotNone(without_plots[0]["mill_name"])

    def test_plot_areas_are_realistic(self):
        self.api.load_example_data()
        conn = database.connect(self.db_path)
        areas = [row[0] for row in conn.execute("SELECT area_ha FROM plots")]
        conn.close()
        for area in areas:
            self.assertGreater(area, 1)
            self.assertLess(area, 2000)

    def test_plots_start_as_not_checked(self):
        self.api.load_example_data()
        conn = database.connect(self.db_path)
        statuses = {row[0] for row in conn.execute("SELECT risk_status FROM plots")}
        conn.close()
        self.assertEqual(statuses, {"not_checked"})

    def test_map_data(self):
        self.api.load_example_data()
        data = self.api.get_map_data()
        self.assertEqual(len(data["mills"]), 5)
        self.assertEqual(len(data["plots"]), 8)
        self.assertEqual(data["plots"][0]["geometry"]["type"], "Polygon")

    def test_map_has_one_sourcing_area_for_mill_only_supplier(self):
        self.api.load_example_data()
        areas = self.api.get_map_data()["sourcing_areas"]
        self.assertEqual(len(areas), 1)
        self.assertEqual(areas[0]["supplier_name"], "PT Demo Borneo Palma")
        self.assertEqual(areas[0]["radius_km"], 50)

    def test_map_data_empty_database(self):
        data = self.api.get_map_data()
        self.assertEqual(data, {"mills": [], "plots": [], "sourcing_areas": [], "hotspots": []})

    def test_reload_keeps_user_suppliers(self):
        conn = database.connect(self.db_path)
        with conn:
            conn.execute("INSERT INTO suppliers (name, certification) VALUES ('My own supplier', 'none')")
        conn.close()

        self.api.load_example_data()
        self.api.load_example_data()
        names = [s["name"] for s in self.api.get_suppliers()]
        self.assertIn("My own supplier", names)
        self.assertEqual(len(names), 6)


if __name__ == "__main__":
    unittest.main()
