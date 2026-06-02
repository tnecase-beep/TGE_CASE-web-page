# post_data.py
import os
import time
import requests

def push_puzzle_submission(*, email: str, cost_eur: float, co2_total_ton: float, details: str, payload: dict, retries: int = 3):
    url = os.environ.get("APPS_SCRIPT_WEBAPP_URL", "").strip()
    secret = os.environ.get("APPS_SCRIPT_SECRET", "").strip()
    if not url or not secret:
        raise RuntimeError("Missing APPS_SCRIPT_WEBAPP_URL or APPS_SCRIPT_SECRET (set in Streamlit secrets/env).")

    body = {
        "secret": secret,
        "email": email,
        "cost_eur": float(cost_eur),
        "co2_total_ton": float(co2_total_ton),
        "details": details,
        "payload": payload,
    }

    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json=body, timeout=20)
            # Apps Script çoğu zaman 200 döner; ok alanını kontrol ediyoruz
            data = r.json() if r.text else {}
            if isinstance(data, dict) and data.get("ok") is True:
                return data
            raise RuntimeError(f"Server error: {data}")
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
