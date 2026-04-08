import logging
import os
import socket
import sys
import time
import traceback
import webbrowser
from pathlib import Path

from error_reporting import ErrorReporter

APP_NAME = "TGECase"
HOST = "127.0.0.1"

PORT_FILE = "tgecase_port.txt"
LOG_FILE = "tgecase.log"
LOCK_FILE = "tgecase.lock"

# Windows single-instance mutex (kalsın)
MUTEX_NAME = "Global\\TGECase_SingleInstance"

_lock_handle = None  # keep process-wide lock alive


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path:
    # Frozen: sys.executable points to the real binary (Windows .exe or macOS .app Contents/MacOS/<bin>)
    # Dev: this file's folder
    return (Path(sys.executable).resolve().parent if is_frozen()
            else Path(__file__).resolve().parent)


def get_app_data_dir() -> Path:
    """
    Writable per-user dir for logs/port/lock.
    - macOS: ~/Library/Application Support/TGECase
    - Windows: %APPDATA%\TGECase
    - Linux: ~/.tgecase
    """
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    else:
        base = Path.home() / f".{APP_NAME.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def acquire_single_instance(data_dir: Path) -> bool:
    """
    Returns True if this is the first instance, False if another is running.
    - Windows: named mutex
    - macOS/Linux: lock file with fcntl
    """
    global _lock_handle

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            CreateMutexW = k.CreateMutexW
            CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
            CreateMutexW.restype = wintypes.HANDLE
            GetLastError = k.GetLastError
            ERROR_ALREADY_EXISTS = 183

            h = CreateMutexW(None, False, MUTEX_NAME)
            if not h:
                return True
            return GetLastError() != ERROR_ALREADY_EXISTS
        except Exception:
            return True

    # Unix-style lock
    try:
        import fcntl
        lock_path = data_dir / LOCK_FILE
        _lock_handle = open(lock_path, "a+", encoding="utf-8")
        fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except Exception:
        return True  # if locking fails, don't block launch


def find_free_port() -> int:
    s = socket.socket()
    s.bind((HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def read_port(data_dir: Path) -> int | None:
    p = data_dir / PORT_FILE
    if not p.exists():
        return None
    try:
        return int(p.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def write_port(data_dir: Path, port: int):
    (data_dir / PORT_FILE).write_text(str(port), encoding="utf-8")


def resolve_total_py() -> Path:
    """
    Locate Total.py in both Windows onedir layout and macOS .app bundle layout.
    We keep your packaging assumption: `--add-data optimize -> app`.
    """
    ed = exe_dir()

    roots: list[Path] = []

    # PyInstaller may set _MEIPASS (especially onefile); harmless to include
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots += [Path(meipass), Path(meipass) / "_internal"]

    # Common layouts
    roots += [
        ed,
        ed / "_internal",
        # macOS app bundle:
        ed.parent / "Resources",
        ed.parent / "Resources" / "_internal",
        ed.parent,            # Contents
        ed.parent.parent,     # <App>.app
    ]

    # de-dup while preserving order
    seen = set()
    uniq_roots = []
    for r in roots:
        rr = r.resolve()
        if rr not in seen:
            seen.add(rr)
            uniq_roots.append(rr)

    candidates: list[Path] = []
    for r in uniq_roots:
        candidates += [
            r / "_internal" / "app" / "Total.py",
            r / "app" / "Total.py",
            r / "optimize" / "Total.py",  # dev fallback
        ]

    for p in candidates:
        if p.exists():
            return p.resolve()

    checked = "\n".join(str(p) for p in candidates)
    raise FileNotFoundError(f"Total.py not found. Checked:\n{checked}")


def main():
    data_dir = get_app_data_dir()
    ed = exe_dir()

    reporter = ErrorReporter(app_name=APP_NAME, data_dir=data_dir)
    reporter.attach_stdio()
    reporter.install_hooks()
    reporter.install_logging_hook()

    os.environ["TGECASE_DATA_DIR"] = str(data_dir)
    os.environ["TGECASE_LOG_FILE"] = str(reporter.log_path)
    os.environ["TGECASE_REPORT_DIR"] = str(reporter.reports_dir)

    reporter.log("=== TGECase launch ===")
    reporter.log(f"Frozen: {is_frozen()}")
    reporter.log(f"Exe dir: {ed}")
    reporter.log(f"Data dir: {data_dir}")

    first = acquire_single_instance(data_dir)
    if not first:
        port = read_port(data_dir) or 8501
        webbrowser.open(f"http://{HOST}:{port}")
        reporter.log("Another instance detected. Opened browser and exiting.")
        return

    total_py = resolve_total_py()
    app_dir = total_py.parent  # .../app
    reporter.log(f"Total.py: {total_py}")
    reporter.log(f"App dir: {app_dir}")

    # Use app_dir as cwd so relative assets resolve (assets/, input files, etc.)
    try:
        os.chdir(app_dir)
    except Exception:
        pass

    port = find_free_port()
    write_port(data_dir, port)
    url = f"http://{HOST}:{port}"
    reporter.log(f"Chosen port: {port}")

    # Streamlit config override
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    # Open browser after a short delay
    import threading
    def open_later():
        time.sleep(1.2)
        webbrowser.open(url)
    threading.Thread(target=open_later, daemon=True).start()

    # Some libs expect help()/quit()/exit() to exist in frozen env
    try:
        import site
    except Exception:
        pass
    try:
        import builtins, pydoc
        if not hasattr(builtins, "help"):
            builtins.help = pydoc.help
        if not hasattr(builtins, "quit"):
            builtins.quit = lambda *a, **k: None
        if not hasattr(builtins, "exit"):
            builtins.exit = lambda *a, **k: None
    except Exception:
        pass

    try:
        import streamlit.web.cli as stcli
        sys.argv = [
            "streamlit", "run", str(total_py),
            "--server.headless=true",
            f"--server.address={HOST}",
            f"--server.port={port}",
            "--browser.gatherUsageStats=false",
            "--global.developmentMode=false",
        ]
        reporter.log(f"Starting Streamlit: {' '.join(sys.argv)}")
        stcli.main()
    except SystemExit:
        reporter.log("Streamlit exited (SystemExit).")
    except Exception:
        reporter.report_exception(
            context="launcher.main",
            extra={"phase": "streamlit_startup"},
        )
        reporter.log("STREAMLIT CRASH:\n" + traceback.format_exc())
    finally:
        try:
            (data_dir / PORT_FILE).unlink(missing_ok=True)
        except Exception:
            pass
        logging.shutdown()


if __name__ == "__main__":
    main()
