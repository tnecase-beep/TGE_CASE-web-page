import json
import logging
import os
import platform
import shutil
import socket
import sys
import threading
import traceback
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any

from crash_config import DEFAULT_ERROR_REPORT_SECRET, DEFAULT_ERROR_REPORT_URL

try:
    import requests
except Exception:  # pragma: no cover - optional network path
    requests = None


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _tail_lines(path: Path, max_lines: int = 200) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    return lines[-max_lines:]


def _configured_report_url() -> str:
    return os.environ.get("TGECASE_ERROR_REPORT_URL", "").strip() or DEFAULT_ERROR_REPORT_URL


def _configured_report_secret() -> str:
    return (
        os.environ.get("TGECASE_ERROR_REPORT_SECRET", "").strip()
        or DEFAULT_ERROR_REPORT_SECRET
    )


class _ExceptionForwardingHandler(logging.Handler):
    def __init__(self, reporter: "ErrorReporter") -> None:
        super().__init__(level=logging.ERROR)
        self.reporter = reporter

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "_tgecase_reported", False):
            return
        if not record.exc_info:
            return

        self.reporter.report_exception(
            context=f"logger:{record.name}",
            exc_info=record.exc_info,
            extra={
                "logger": record.name,
                "level": record.levelname,
                "message": record.getMessage(),
            },
        )


class ErrorReporter:
    def __init__(self, *, app_name: str, data_dir: Path) -> None:
        self.app_name = app_name
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.data_dir / "tgecase.log"
        self.reports_dir = self.data_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._log_handle = None
        self._reported_fingerprints: set[str] = set()
        self._lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._handler: logging.Handler | None = None

    def attach_stdio(self) -> None:
        if self._log_handle is not None:
            return

        self._log_handle = open(
            self.log_path,
            "a",
            encoding="utf-8",
            buffering=1,
        )
        sys.stdout = self._log_handle
        sys.stderr = self._log_handle

    def install_hooks(self) -> None:
        previous_excepthook = sys.excepthook

        def handle_exception(exc_type, exc_value, exc_traceback) -> None:
            if exc_type is KeyboardInterrupt:
                previous_excepthook(exc_type, exc_value, exc_traceback)
                return

            self.report_exception(
                context="sys.excepthook",
                exc_info=(exc_type, exc_value, exc_traceback),
            )
            previous_excepthook(exc_type, exc_value, exc_traceback)

        sys.excepthook = handle_exception

        if hasattr(threading, "excepthook"):
            previous_threading_hook = threading.excepthook

            def handle_thread_exception(args) -> None:
                self.report_exception(
                    context=f"thread:{getattr(args.thread, 'name', 'unknown')}",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                )
                previous_threading_hook(args)

            threading.excepthook = handle_thread_exception

    def install_logging_hook(self) -> None:
        if self._handler is not None:
            return

        self._handler = _ExceptionForwardingHandler(self)
        for logger_name in ("", "streamlit", "tornado", "asyncio"):
            logging.getLogger(logger_name).addHandler(self._handler)

    def log(self, message: str) -> None:
        if self._log_handle is None:
            self.attach_stdio()

        with self._lock:
            timestamp = _utc_now_iso()
            self._log_handle.write(f"[{timestamp}] {message}\n")
            self._log_handle.flush()

    def report_exception(
        self,
        *,
        context: str,
        exc_info=None,
        extra: dict[str, Any] | None = None,
    ) -> Path | None:
        if exc_info is None:
            exc_info = sys.exc_info()

        exc_type, exc_value, exc_traceback = exc_info
        if exc_type is None:
            return None

        traceback_text = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        fingerprint = sha1(
            f"{context}\n{traceback_text}".encode("utf-8", errors="replace")
        ).hexdigest()[:16]

        with self._lock:
            if fingerprint in self._reported_fingerprints:
                return None
            self._reported_fingerprints.add(fingerprint)

        report = {
            "app_name": self.app_name,
            "timestamp_utc": _utc_now_iso(),
            "context": context,
            "fingerprint": fingerprint,
            "exception_type": getattr(exc_type, "__name__", str(exc_type)),
            "exception_message": str(exc_value),
            "traceback": traceback_text,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python": sys.version,
                "hostname": socket.gethostname(),
                "frozen": bool(getattr(sys, "frozen", False)),
            },
            "paths": {
                "cwd": str(Path.cwd()),
                "executable": str(Path(sys.executable).resolve()),
                "data_dir": str(self.data_dir),
                "log_path": str(self.log_path),
            },
            "environment": {
                "TGECASE_ERROR_REPORT_URL": _configured_report_url(),
                "TGECASE_BUILD_VERSION": os.environ.get("TGECASE_BUILD_VERSION", ""),
            },
            "log_tail": _tail_lines(self.log_path),
        }
        if extra:
            report["extra"] = extra

        report_path = self.reports_dir / (
            f"crash-{report['timestamp_utc'].replace(':', '').replace('-', '')}"
            f"-{fingerprint}.json"
        )
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.log(
            f"Crash report saved: {report_path.name} "
            f"(context={context}, fingerprint={fingerprint})"
        )
        self._mirror_report(report_path)
        self._send_remote(report, report_path)
        return report_path

    def _mirror_report(self, report_path: Path) -> None:
        mirror_dir_raw = os.environ.get("TGECASE_REPORT_MIRROR_DIR", "").strip()
        if not mirror_dir_raw:
            return

        try:
            mirror_dir = Path(mirror_dir_raw).expanduser()
            mirror_dir.mkdir(parents=True, exist_ok=True)
            mirrored_path = mirror_dir / report_path.name
            shutil.copy2(report_path, mirrored_path)
            self.log(f"Crash report mirrored: {mirrored_path}")
        except Exception as exc:
            self.log(f"Crash report mirror failed for {report_path.name}: {exc}")

    def _send_remote(self, report: dict[str, Any], report_path: Path) -> None:
        url = _configured_report_url()
        if not url or requests is None:
            return

        if not self._send_lock.acquire(blocking=False):
            return

        try:
            headers = {"Content-Type": "application/json"}
            token = os.environ.get("TGECASE_ERROR_REPORT_TOKEN", "").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"

            payload = dict(report)
            secret = _configured_report_secret()
            if secret:
                payload["secret"] = secret

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            self.log(f"Crash report uploaded: {report_path.name}")
        except Exception as exc:  # pragma: no cover - network path
            self.log(f"Crash report upload failed for {report_path.name}: {exc}")
        finally:
            self._send_lock.release()
