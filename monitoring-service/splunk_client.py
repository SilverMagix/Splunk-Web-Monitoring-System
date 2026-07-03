import os

import requests


def send_to_splunk(event: dict) -> None:
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
            verify=os.getenv("SPLUNK_HEC_VERIFY", "false").lower() == "true",
        )
    except Exception:
        pass
