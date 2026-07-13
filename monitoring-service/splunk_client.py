"""Thin Splunk HTTP Event Collector (HEC) client used by the monitoring service."""

import os

import requests


def send_to_splunk(event: dict) -> None:
    """
    POST a single event to Splunk HEC.

    No-ops if SPLUNK_HEC_URL / SPLUNK_TOKEN are missing.
    Swallows network errors so the ingest API stays available when Splunk is down.
    """
    url = os.getenv("SPLUNK_HEC_URL")
    token = os.getenv("SPLUNK_TOKEN")
    if not url or not token:
        return

    payload = {
        "event": event,
        "sourcetype": "web_app_logs",
    }

    try:
        requests.post(
            url,
            headers={"Authorization": f"Splunk {token}"},
            json=payload,
            timeout=2,
            # Demo uses Splunk's self-signed cert; set SPLUNK_HEC_VERIFY=true to enforce TLS.
            verify=os.getenv("SPLUNK_HEC_VERIFY", "false").lower() == "true",
        )
    except Exception:
        pass
