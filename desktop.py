"""Desktop wrapper: runs the existing FastAPI app inside a native window.

This is purely additive — it reuses app.main untouched. Same bring-your-own-key,
same stateless (no-retention) behavior, just in a desktop window instead of a
browser tab. Packaged into a double-click .app / .exe by PyInstaller (see build/).

Run from source:  python desktop.py
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request

import uvicorn

from app.main import app

APP_NAME = "RESOPT"

# Disable rate limiting and size restrictions for the local desktop instance
os.environ["RESOPT_DISABLE_RATELIMIT"] = "1"
os.environ["RESOPT_MAX_UPLOAD_BYTES"] = str(50 * 1024 * 1024)
os.environ["RESOPT_MAX_REQUEST_BYTES"] = str(100 * 1024 * 1024)

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# A STABLE port keeps the webview origin (http://127.0.0.1:<port>) constant across
# launches, so the browser-side localStorage that holds the saved Profile is found
# again on reopen. A random port looks like a brand-new origin every time, which is
# why the Profile appeared to reset. Fall back to a random free port only if it's taken.
_PREFERRED_PORT = int(os.environ.get("RESOPT_PORT", "47615"))


def _pick_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", _PREFERRED_PORT))
        return _PREFERRED_PORT
    except OSError:
        return _free_port()


def _storage_dir() -> str:
    """Persistent per-user dir where the webview keeps HTML5 localStorage (the Profile)."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def start_server() -> int:
    """Start uvicorn on a free localhost port in a daemon thread; return the port.

    Signal handlers are disabled because the server runs off the main thread.
    """
    port = _pick_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # off-main-thread

    threading.Thread(target=server.run, daemon=True, name="uvicorn").start()

    # Wait until the API answers (up to ~15s) before showing the window.
    health = f"http://127.0.0.1:{port}/api/health"
    for _ in range(150):
        try:
            with urllib.request.urlopen(health, timeout=1) as r:
                if r.status == 200:
                    return port
        except Exception:
            time.sleep(0.1)
    return port  # show the window anyway; it will retry on load


def selftest() -> int:
    """Boot the bundled server and confirm it serves, then exit. No GUI.

    Used to verify a packaged build actually runs (catches missing hidden imports).
    Returns a process exit code.
    """
    port = start_server()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as r:
            ok = r.status == 200
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            ok = ok and r.status == 200
        # Verify bundled data files actually LOAD (the taxonomy JSON is a PyInstaller
        # gotcha — present on disk but unreachable via dirname(__file__) in a bundle).
        from app.workflow.taxonomy_resolver import _load_taxonomy
        if not _load_taxonomy():
            ok = False
            print("SELFTEST: master_taxonomy.json not reachable in bundle")
        # Prove complete_json strips U+2028 BEFORE the provider call (the PDF crash).
        # Monkeypatch the SDK impl to capture what reaches it — offline, no network.
        from app.llm.client import LLMClient
        _c = LLMClient(provider="anthropic", api_key="sk-ant-selftest-offline")
        _seen = {}
        _c._impl = lambda ctx, instr, budget, model: (
            _seen.update(ctx=ctx, instr=instr), ("{}", 1, 1, False))[1]
        _c.complete_json("ctx" + chr(0x2028) + "tail", "instr" + chr(0x2028),
                         mock=None, max_retries=1)
        if chr(0x2028) in _seen.get("ctx", "") or chr(0x2028) in _seen.get("instr", ""):
            ok = False
            print("SELFTEST: complete_json does NOT strip U+2028 — crash fix not active")
        print("SELFTEST OK" if ok else "SELFTEST FAILED")
        return 0 if ok else 1
    except Exception as e:  # noqa: BLE001
        print(f"SELFTEST FAILED: {e}")
        return 1


class _Api:
    """Native bridge so the desktop app saves the .docx with the correct name.

    Webviews don't honor the browser <a download="name"> on blob URLs (they save
    as "Unknown"), so the frontend hands us the bytes + filename and we show a real
    save dialog.
    """

    def save_docx(self, b64: str, filename: str) -> dict:
        import base64
        import webview
        try:
            data = base64.b64decode(b64)
            win = webview.windows[0]
            res = win.create_file_dialog(
                webview.SAVE_DIALOG, save_filename=(filename or "resume.docx"))
            if not res:
                return {"ok": False, "cancelled": True}
            path = res[0] if isinstance(res, (list, tuple)) else res
            ext = ".pdf" if (filename or "").lower().endswith(".pdf") else ".docx"
            if not path.lower().endswith(ext):
                path += ext
            with open(path, "wb") as f:
                f.write(data)
            return {"ok": True, "path": path}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}


def main() -> None:
    import webview  # imported lazily so the server logic is testable without a GUI

    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
    except Exception:
        pass

    port = start_server()
    webview.create_window(APP_NAME, f"http://127.0.0.1:{port}", js_api=_Api(),
                          width=1180, height=900, min_size=(900, 640))
    # private_mode=False + a stable storage_path so the saved Profile persists across
    # restarts. The default private mode wipes HTML5 localStorage on close, which is
    # why the app kept starting over from profile building.
    webview.start(private_mode=False, storage_path=_storage_dir())


if __name__ == "__main__":
    import sys
    raise SystemExit(selftest() if "--selftest" in sys.argv else (main() or 0))
