"""Functions the interface (JavaScript) is allowed to call.

pywebview makes every public method of Api available in JavaScript as
window.pywebview.api.<method_name>().
"""

import json
import subprocess
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

import webview
from shapely.geometry import mapping

from app import database
from app.checks import fire, forest, get_suppliers_with_details
from app.demo import load_demo_data
from app.formatting import format_date
from app.report import ReportError, build_report


def _open_with_system(path, reveal=False):
    """Open a file with its default app, or show it in Finder / Explorer."""
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)] if reveal else ["open", str(path)], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{path}"] if reveal else ["explorer", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path.parent if reveal else path)], check=False)


class Api:
    def __init__(self, db_path=database.DEFAULT_DB_PATH):
        # Leading underscores keep these hidden from JavaScript.
        self._db_path = db_path
        self._last_report = None  # only the report we just saved can be opened

    def load_example_data(self):
        with closing(database.connect(self._db_path)) as conn:
            count = load_demo_data(conn)
        return {"suppliers_loaded": count}

    def get_suppliers(self):
        with closing(database.connect(self._db_path)) as conn:
            return get_suppliers_with_details(conn)

    def run_checks(self):
        with closing(database.connect(self._db_path)) as conn:
            fire.run_fire_check(conn)
            forest.run_forest_check(conn)
            database.update_plot_risk_status(conn)
            return database.get_last_check(conn)

    def get_last_check(self):
        with closing(database.connect(self._db_path)) as conn:
            return database.get_last_check(conn)

    def export_report(self):
        """Ask where to save, then write the PDF.

        Returns {"saved": True, "file_name", "folder", "pages"}, {"saved": False} if
        the user cancelled, or {"saved": False, "error": "..."} with a plain message.
        """
        with closing(database.connect(self._db_path)) as conn:
            if not database.get_last_check(conn)["checked_at"]:
                return {"saved": False, "error": "Check your suppliers first, then export the report."}

        chosen = webview.windows[0].create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(Path.home() / "Documents"),
            save_filename=f"Supplier risk report {format_date(date.today())}.pdf",
            file_types=("PDF files (*.pdf)",),
        )
        if not chosen:
            return {"saved": False}
        path = Path(chosen if isinstance(chosen, str) else chosen[0])
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")

        try:
            with closing(database.connect(self._db_path)) as conn:
                result = build_report(conn, path)
        except ReportError as error:
            return {"saved": False, "error": str(error)}
        except OSError:
            return {"saved": False, "error": "The report could not be saved there. Try another folder."}

        self._last_report = path
        folder = str(path.parent).replace(str(Path.home()), "~", 1)  # e.g. ~/Documents
        return {"saved": True, "file_name": path.name, "folder": folder, "pages": result["pages"]}

    def open_report(self):
        if self._last_report and self._last_report.exists():
            _open_with_system(self._last_report)

    def show_report_in_finder(self):
        if self._last_report and self._last_report.exists():
            _open_with_system(self._last_report, reveal=True)

    def get_map_data(self):
        with closing(database.connect(self._db_path)) as conn:
            data = database.get_map_data(conn)
            data["hotspots"] = fire.relevant_hotspots(conn)
            data["forest_2020"] = [json.loads(row[0]) for row in conn.execute("SELECT geometry FROM forest_2020")]
            _, deforestation = forest.load_deforestation(conn)
            data["forest_loss"] = [{"geometry": mapping(d["shape"]), "year": d["year"]} for d in deforestation]
            return data
