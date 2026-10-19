"""Functions the interface (JavaScript) is allowed to call.

pywebview makes every public method of Api available in JavaScript as
window.pywebview.api.<method_name>().
"""

from contextlib import closing

from app import database
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
