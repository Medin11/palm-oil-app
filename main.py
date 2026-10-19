"""Start the Palm Oil Supply Chain Checker desktop app.

Opens a native window and shows the interface from the ui/ folder.
"""

from pathlib import Path

import webview

APP_TITLE = "Palm Oil Supply Chain Checker"
UI_FOLDER = Path(__file__).parent / "ui"


def main():
    webview.create_window(
        APP_TITLE,
        str(UI_FOLDER / "index.html"),
        width=1200,
        height=800,
        min_size=(900, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
