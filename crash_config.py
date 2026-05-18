"""
TGE Case – error reporting configuration.

Override any of these defaults via environment variables or Streamlit secrets.
For Streamlit Cloud, add to .streamlit/secrets.toml:

    notify_email   = "you@example.com"
    smtp_from      = "sender@gmail.com"
    smtp_password  = "your-gmail-app-password"
    # smtp_host    = "smtp.gmail.com"   # optional, this is the default
    # smtp_port    = "587"              # optional, this is the default

Environment-variable equivalents (override secrets):
    TGECASE_ERROR_REPORTING_ENABLED – master on/off switch (default: true)
    TGECASE_ERROR_EMAIL_ENABLED     – email channel on/off switch (default: true)
    TGECASE_NOTIFY_EMAIL    – recipient address
    TGECASE_SMTP_FROM       – sender address
    TGECASE_SMTP_PASSWORD   – SMTP / Gmail app password
    TGECASE_SMTP_HOST       – SMTP host  (default: smtp.gmail.com)
    TGECASE_SMTP_PORT       – SMTP port  (default: 587)
    TGECASE_ERROR_REPORT_URL    – optional webhook URL
    TGECASE_ERROR_REPORT_SECRET – optional webhook secret
"""

# ------------------------------------------------------------------
# Webhook (Google Apps Script) – secondary channel, optional
# ------------------------------------------------------------------
DEFAULT_ERROR_REPORT_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzyYULrLOUl9AZEUXPBJ-5dIrOT-DGZKLB8vQOkeZYA_mzw9wrNZOLs8vaqf84m8_Ih/exec"
)
DEFAULT_ERROR_REPORT_SECRET = "TGECASE-2026-UZH-8d31f4c9b2e7"
DEFAULT_ERROR_REPORTING_ENABLED = False
DEFAULT_ERROR_WEBHOOK_ENABLED = False

# ------------------------------------------------------------------
# E-mail (SMTP) – primary channel
# Set these so the module can send you mail directly.
# ------------------------------------------------------------------
DEFAULT_ERROR_EMAIL_ENABLED = False
DEFAULT_NOTIFY_EMAIL = ""   # e.g. "you@example.com"
DEFAULT_SMTP_FROM    = ""   # e.g. "sender@gmail.com"
DEFAULT_SMTP_HOST    = "smtp.gmail.com"
DEFAULT_SMTP_PORT    = 587
