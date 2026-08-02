"""Desktop app launcher — run the whole thing as one openable window.

Starts the FastAPI server (which also serves the built UI, see ``api._mount_ui``)
on a background thread, waits for it, then opens a native window pointing at it.
Everything stays local: same Ollama privacy model, same on-disk token.

Prereqs (one time):
    uv sync --extra web --extra desktop --extra gmail
    DESKTOP=1 npm --prefix web run build     # produces web/out/

Then launch it with ``inbox-agent app``.
"""

from __future__ import annotations

import threading
import time
import urllib.request

_HOST = "127.0.0.1"
_PORT = 8000
_URL = f"http://{_HOST}:{_PORT}"


def _serve() -> None:
    import uvicorn

    from inbox_agent.api import app

    uvicorn.run(app, host=_HOST, port=_PORT, log_level="warning")


def _wait_until_up(timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"{_URL}/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    try:
        import webview  # pywebview
    except ImportError as exc:
        raise SystemExit(
            "The desktop app needs the desktop extra:\n    uv sync --extra desktop"
        ) from exc

    threading.Thread(target=_serve, daemon=True).start()
    if not _wait_until_up():
        raise SystemExit(f"The API did not come up at {_URL}. Is the UI built (web/out)?")

    webview.create_window("Postwise", _URL, width=1240, height=840, min_size=(900, 600))
    webview.start()


if __name__ == "__main__":
    main()
