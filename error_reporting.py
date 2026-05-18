"""
TGE Case – centralised error reporting.

Usage (add near the top of Total.py, before other imports):

    from error_reporting import get_reporter as _get_reporter
    _get_reporter()          # initialises singleton, patches st.error

In launcher.py you can still call:

    reporter = get_reporter()
    reporter.attach_stdio()  # optional: redirect stdout/stderr to log file
"""

import json
import logging
import os
import platform
import smtplib
import socket
import sys
import tempfile
import threading
import traceback
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from hashlib import sha1
from pathlib import Path
from typing import Any

from crash_config import (
    DEFAULT_ERROR_EMAIL_ENABLED,
    DEFAULT_ERROR_REPORTING_ENABLED,
    DEFAULT_ERROR_REPORT_SECRET,
    DEFAULT_ERROR_REPORT_URL,
    DEFAULT_ERROR_WEBHOOK_ENABLED,
    DEFAULT_NOTIFY_EMAIL,
    DEFAULT_SMTP_FROM,
    DEFAULT_SMTP_HOST,
    DEFAULT_SMTP_PORT,
)

try:
    import requests
except Exception:
    requests = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TGECASE_ERROR_REPORTING_ENABLED = False

def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _get_secret(env_key: str, secrets_key: str, default: str = "") -> str:
    """Priority: env var → Streamlit secrets → default."""
    val = os.environ.get(env_key, "").strip()
    if val:
        return val
    try:
        import streamlit as st
        val = str(st.secrets.get(secrets_key, "")).strip()
        if val:
            return val
    except Exception:
        pass
    return default


def _get_bool_config(env_key: str, secrets_key: str, default: bool = True) -> bool:
    """Read a boolean flag from env vars or Streamlit secrets."""
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        try:
            import streamlit as st
            value = st.secrets.get(secrets_key, None)
            if value is not None:
                raw = str(value).strip()
        except Exception:
            pass
    if not raw:
        return default
    return raw.lower() not in {"0", "false", "no", "off", "disabled"}


def _default_data_dir() -> Path:
    if os.environ.get("TGECASE_DATA_DIR"):
        return Path(os.environ["TGECASE_DATA_DIR"])
    return Path(tempfile.gettempdir()) / "tgecase"


# ---------------------------------------------------------------------------
# Logging handler
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------
TGECASE_ERROR_REPORTING_ENABLED = False

class ErrorReporter:
    def __init__(self, *, app_name: str, data_dir: Path | None = None) -> None:
        self.app_name = app_name
        self.enabled = _get_bool_config(
            "TGECASE_ERROR_REPORTING_ENABLED",
            "error_reporting_enabled",
            DEFAULT_ERROR_REPORTING_ENABLED,
        )
        self.data_dir = data_dir or _default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.data_dir / "tgecase.log"
        self.reports_dir = self.data_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self._log_handle = None
        self._reported_fingerprints: set[str] = set()
        self._lock = threading.RLock()
        self._handler: logging.Handler | None = None
        self._st_patched = False

    # ------------------------------------------------------------------
    # Optional: redirect stdout/stderr to log file (launcher only)
    # Do NOT call this inside a running Streamlit process.
    # ------------------------------------------------------------------

    def attach_stdio(self) -> None:
        if self._log_handle is not None:
            return
        self._log_handle = open(
            self.log_path, "a", encoding="utf-8", buffering=1
        )
        sys.stdout = self._log_handle
        sys.stderr = self._log_handle

    # ------------------------------------------------------------------
    # Hook installation
    # ------------------------------------------------------------------

    def install_hooks(self) -> None:
        """Install sys.excepthook and threading.excepthook."""
        if not self.enabled:
            return
        previous_excepthook = sys.excepthook

        def handle_exception(exc_type, exc_value, exc_tb):
            if exc_type is KeyboardInterrupt:
                previous_excepthook(exc_type, exc_value, exc_tb)
                return
            self.report_exception(
                context="sys.excepthook",
                exc_info=(exc_type, exc_value, exc_tb),
            )
            previous_excepthook(exc_type, exc_value, exc_tb)

        sys.excepthook = handle_exception

        if hasattr(threading, "excepthook"):
            previous_threading_hook = threading.excepthook

            def handle_thread_exception(args):
                self.report_exception(
                    context=f"thread:{getattr(args.thread, 'name', 'unknown')}",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                )
                previous_threading_hook(args)

            threading.excepthook = handle_thread_exception

    def install_logging_hook(self) -> None:
        """Forward ERROR-level log records that carry exception info."""
        if not self.enabled:
            return
        if self._handler is not None:
            return
        self._handler = _ExceptionForwardingHandler(self)
        for name in ("", "streamlit", "tornado", "asyncio"):
            logging.getLogger(name).addHandler(self._handler)

    def install_streamlit_hooks(self) -> None:
        """
        Monkey-patch st.error and st.exception so every call is also reported.
        Idempotent – safe to call multiple times.
        """
        if not self.enabled:
            return
        if self._st_patched:
            return
        try:
            import streamlit as st

            _orig_error = st.error
            _orig_exception = st.exception
            _self = self

            def _patched_error(body, *, icon=None):
                _self.report_st_error(str(body))
                if icon is not None:
                    return _orig_error(body, icon=icon)
                return _orig_error(body)

            def _patched_exception(exception):
                _self.report_exception(
                    context="st.exception",
                    exc_info=(
                        type(exception),
                        exception,
                        exception.__traceback__,
                    ),
                )
                return _orig_exception(exception)

            st.error = _patched_error
            st.exception = _patched_exception
            self._st_patched = True
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public reporting API
    # ------------------------------------------------------------------

    def log(self, message: str) -> None:
        try:
            ts = _utc_now_iso()
            with open(self.log_path, "a", encoding="utf-8", buffering=1) as fh:
                fh.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def report_st_error(self, message: str) -> None:
        """Report an explicit st.error() call."""
        if not self.enabled:
            return
        fingerprint = sha1(
            f"st.error\n{message}".encode("utf-8", errors="replace")
        ).hexdigest()[:16]

        with self._lock:
            if fingerprint in self._reported_fingerprints:
                return
            self._reported_fingerprints.add(fingerprint)

        report = self._build_report(
            context="st.error",
            fingerprint=fingerprint,
            exception_type="st.error",
            exception_message=message,
            traceback_text="(no traceback – explicit st.error call)",
        )
        self._save_and_send(report)

    def report_exception(
        self,
        *,
        context: str,
        exc_info=None,
        extra: dict[str, Any] | None = None,
    ) -> Path | None:
        if not self.enabled:
            return None
        if exc_info is None:
            exc_info = sys.exc_info()

        exc_type, exc_value, exc_tb = exc_info
        if exc_type is None:
            return None

        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        fingerprint = sha1(
            f"{context}\n{tb_text}".encode("utf-8", errors="replace")
        ).hexdigest()[:16]

        with self._lock:
            if fingerprint in self._reported_fingerprints:
                return None
            self._reported_fingerprints.add(fingerprint)

        report = self._build_report(
            context=context,
            fingerprint=fingerprint,
            exception_type=getattr(exc_type, "__name__", str(exc_type)),
            exception_message=str(exc_value),
            traceback_text=tb_text,
            extra=extra,
        )
        return self._save_and_send(report)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_report(
        self,
        *,
        context: str,
        fingerprint: str,
        exception_type: str,
        exception_message: str,
        traceback_text: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report: dict[str, Any] = {
            "app_name": self.app_name,
            "timestamp_utc": _utc_now_iso(),
            "context": context,
            "fingerprint": fingerprint,
            "exception_type": exception_type,
            "exception_message": exception_message,
            "traceback": traceback_text,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": sys.version,
                "hostname": socket.gethostname(),
            },
            "paths": {
                "cwd": str(Path.cwd()),
                "data_dir": str(self.data_dir),
            },
        }
        if extra:
            report["extra"] = extra
        return report

    def _save_and_send(self, report: dict[str, Any]) -> Path:
        ts = report["timestamp_utc"].replace(":", "").replace("-", "")
        fp = report["fingerprint"]
        report_path = self.reports_dir / f"crash-{ts}-{fp}.json"
        try:
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.log(
                f"Report saved: {report_path.name} "
                f"(context={report['context']}, fp={fp})"
            )
        except Exception as exc:
            self.log(f"Report save failed: {exc}")

        # Fire-and-forget so UI is never blocked
        threading.Thread(
            target=self._send_all,
            args=(report, report_path),
            daemon=True,
        ).start()
        return report_path

    def _send_all(self, report: dict[str, Any], report_path: Path) -> None:
        if not self.enabled:
            return
        self._send_email(report)
        self._send_webhook(report, report_path)

    def _send_email(self, report: dict[str, Any]) -> None:
        if not _get_bool_config(
            "TGECASE_ERROR_EMAIL_ENABLED",
            "error_email_enabled",
            DEFAULT_ERROR_EMAIL_ENABLED,
        ):
            self.log("Email skipped: error email reporting disabled.")
            return

        to_addr  = _get_secret("TGECASE_NOTIFY_EMAIL",  "notify_email",  DEFAULT_NOTIFY_EMAIL)
        from_addr = _get_secret("TGECASE_SMTP_FROM",    "smtp_from",     DEFAULT_SMTP_FROM)
        password = _get_secret("TGECASE_SMTP_PASSWORD", "smtp_password", "")
        host     = _get_secret("TGECASE_SMTP_HOST",     "smtp_host",     DEFAULT_SMTP_HOST)
        port     = int(_get_secret("TGECASE_SMTP_PORT", "smtp_port",     str(DEFAULT_SMTP_PORT)) or DEFAULT_SMTP_PORT)

        if not (to_addr and from_addr and password):
            self.log("Email skipped: SMTP credentials not configured.")
            return

        subject = (
            f"[{self.app_name}] {report['exception_type']} "
            f"in {report['context']} – {report['timestamp_utc']}"
        )
        body = (
            f"App:         {report['app_name']}\n"
            f"Time (UTC):  {report['timestamp_utc']}\n"
            f"Context:     {report['context']}\n"
            f"Error:       {report['exception_type']}: {report['exception_message']}\n"
            f"Fingerprint: {report['fingerprint']}\n"
            f"Host:        {report['platform'].get('hostname', '')}\n\n"
            f"--- Traceback ---\n{report['traceback']}\n"
        )

        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(from_addr, password)
                smtp.sendmail(from_addr, to_addr, msg.as_string())
            self.log(f"Email sent → {to_addr} (fp={report['fingerprint']})")
        except Exception as exc:
            self.log(f"Email failed: {exc}")

    def _send_webhook(self, report: dict[str, Any], report_path: Path) -> None:
        if not _get_bool_config(
            "TGECASE_ERROR_WEBHOOK_ENABLED",
            "error_webhook_enabled",
            DEFAULT_ERROR_WEBHOOK_ENABLED,
        ):
            self.log("Webhook skipped: error webhook reporting disabled.")
            return
        url = (
            os.environ.get("TGECASE_ERROR_REPORT_URL", "").strip()
            or DEFAULT_ERROR_REPORT_URL
        )
        if not url or requests is None:
            return
        try:
            payload = dict(report)
            secret = (
                os.environ.get("TGECASE_ERROR_REPORT_SECRET", "").strip()
                or DEFAULT_ERROR_REPORT_SECRET
            )
            if secret:
                payload["secret"] = secret
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            self.log(f"Webhook sent: {report_path.name}")
        except Exception as exc:
            self.log(f"Webhook failed for {report_path.name}: {exc}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_reporter: ErrorReporter | None = None
_init_lock = threading.Lock()


def get_reporter(app_name: str = "TGE Case") -> ErrorReporter:
    """
    Return (and lazily create) the global ErrorReporter singleton.
    Also installs all hooks on first call.
    """
    global _reporter
    if _reporter is not None:
        return _reporter
    with _init_lock:
        if _reporter is None:
            _reporter = ErrorReporter(
                app_name=app_name,
                data_dir=_default_data_dir(),
            )
            _reporter.install_hooks()
            _reporter.install_logging_hook()
            _reporter.install_streamlit_hooks()
    return _reporter
