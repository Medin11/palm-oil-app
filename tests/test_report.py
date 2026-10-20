"""Checks for the PDF report and the shared result wording.

Run with:  .venv/bin/python -m unittest discover tests
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app import database
from app.checks import fire, forest, get_suppliers_with_details
from app.demo import load_demo_data
from app.formatting import format_date, format_hectares, format_km
from app.report import ReportError, build_report, sorted_suppliers


class FormattingTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(format_date("2026-09-14"), "14 Sep 2026")
        self.assertEqual(format_date("2026-10-20T02:12:00"), "20 Oct 2026")
        self.assertEqual(format_hectares(1000.47), "1,000 ha")
        self.assertEqual(format_hectares(2.84), "2.8 ha")
        self.assertEqual(format_hectares(0), "0 ha")
        self.assertEqual(format_km(2.0), "2 km")
        self.assertEqual(format_km(0.7), "0.7 km")


class DetailLineTests(unittest.TestCase):
    def test_fire_lines(self):
        details = {"fires_on_plot": 2, "fires_nearby": 2, "nearby_km": 5.0, "nearest_km": 0.0,
                   "nearest_date": "2026-09-03", "nearest_satellite": "VIIRS (NOAA-20)"}
        self.assertEqual(
            fire.detail_lines(details, is_mill=False),
            ["2 fires on the plot", "Nearest fire: on the plot, 3 Sep 2026 (VIIRS (NOAA-20))"],
        )

    def test_forest_lines(self):
        details = {"forest_2020_ha": 58.8, "cleared_ha": 13.6, "cleared_years": [2023], "nearby_km": 1.0,
                   "nearest_km": 0.0, "nearest_year": 2023}
        self.assertEqual(
            forest.detail_lines(details, is_mill=False),
            ["Forest on the plot on 31 Dec 2020: 59 ha", "Cleared since 2021: 14 ha (2023)",
             "Nearest clearing: on the plot (2023)"],
        )


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        self.conn = database.connect(self.folder / "test.db")
        load_demo_data(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def run_checks(self):
        fire.run_fire_check(self.conn, today=date(2026, 10, 20))
        forest.run_forest_check(self.conn)
        database.update_plot_risk_status(self.conn)

    def test_export_before_check_gives_clear_message(self):
        with self.assertRaises(ReportError) as caught:
            build_report(self.conn, self.folder / "report.pdf")
        self.assertIn("Check your suppliers first", str(caught.exception))
        self.assertFalse((self.folder / "report.pdf").exists())

    def test_creates_pdf_with_all_sections(self):
        self.run_checks()
        path = self.folder / "report.pdf"
        result = build_report(self.conn, path, compress=False)
        data = path.read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        # cover + summary + 5 supplier pages + method + appendix
        self.assertEqual(result["pages"], 9)
        self.assertEqual(result["suppliers"], 5)
        for text in (b"Summary", b"Method and limits", b"Appendix: plot locations", b"PT Demo Sawit Lestari"):
            self.assertIn(text, data)

    def test_demo_data_is_labelled(self):
        self.run_checks()
        path = self.folder / "report.pdf"
        build_report(self.conn, path, compress=False)
        self.assertIn(b"Contains simulated demo data", path.read_bytes())

    def test_worst_suppliers_come_first(self):
        self.run_checks()
        names = [s["name"] for s in sorted_suppliers(get_suppliers_with_details(self.conn))]
        self.assertEqual(
            names,
            ["CV Demo Tunas Baru", "PT Demo Sawit Lestari", "PT Demo Agro Kapuas", "PT Demo Borneo Palma",
             "Koperasi Demo Tani Makmur"],
        )


if __name__ == "__main__":
    unittest.main()
