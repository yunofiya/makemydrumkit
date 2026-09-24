"""Double-click-friendly launcher: starts the app and opens your browser
to it automatically. Used by "RUN ME.bat" / "RUN ME.command" — you can
also just run this directly with `python run_server.py`."""

import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mythkit.app import PORT, app  # noqa: E402


def _open_browser_when_ready():
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    print(f"\nStarting MAKEMYDRUMKIT at http://localhost:{PORT}")
    print("Your browser should open automatically in a couple seconds.")
    print("Keep this window open while you use the app — closing it stops the app.\n")
    app.run(host="127.0.0.1", port=PORT)
