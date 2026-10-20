"""Functions the interface (JavaScript) is allowed to call.

pywebview makes every public method of Api available in JavaScript as
window.pywebview.api.<method_name>().
"""

import json
from contextlib import closing

from shapely.geometry import mapping

from app import database
from app.checks import fire, forest
from app.demo import load_demo_data


class Api:
    def __init__(self, db_path=database.DEFAULT_DB_PATH):
        # Leading underscore keeps this hidden from JavaScript.
        self._db_path = db_path

    def load_example_data(self):
        with closing(database.connect(self._db_path)) as conn:
            count = load_demo_data(conn)
        return {"suppliers_loaded": count}

    def get_suppliers(self):
        with closing(database.connect(self._db_path)) as conn:
            return database.get_suppliers(conn)

    def run_checks(self):
        with closing(database.connect(self._db_path)) as conn:
            fire.run_fire_check(conn)
            forest.run_forest_check(conn)
            database.update_plot_risk_status(conn)
            return database.get_last_check(conn)

    def get_last_check(self):
        with closing(database.connect(self._db_path)) as conn:
            return database.get_last_check(conn)

    def get_map_data(self):
        with closing(database.connect(self._db_path)) as conn:
            data = database.get_map_data(conn)
            data["hotspots"] = fire.relevant_hotspots(conn)
            data["forest_2020"] = [json.loads(row[0]) for row in conn.execute("SELECT geometry FROM forest_2020")]
            _, deforestation = forest.load_deforestation(conn)
            data["forest_loss"] = [{"geometry": mapping(d["shape"]), "year": d["year"]} for d in deforestation]
            return data
