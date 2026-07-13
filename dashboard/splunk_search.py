"""Splunk REST helpers: run SPL searches and shape results for the dashboard UI."""

from urllib.parse import urlparse, urlunparse

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

# Map UI range keys to Splunk earliest= values.
RANGE_MAP = {
    "15m": "-15m",
    "1h": "-1h",
    "24h": "-24h",
}

DOCKER_SPLUNK_HOST = "splunk"
DOCKER_SPLUNK_PORT = 8089


def normalize_splunk_url(url: str) -> str:
    """Map localhost URLs to the Docker Compose service hostname `splunk`."""
    cleaned = url.strip().rstrip("/")
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    port = parsed.port or DOCKER_SPLUNK_PORT

    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        return urlunparse(parsed._replace(netloc=f"{DOCKER_SPLUNK_HOST}:{port}"))

    return cleaned


@dataclass
class SplunkConfig:
    """Connection settings for Splunk management port (REST API)."""

    url: str
    user: str
    password: str
    verify_ssl: bool = False  # HEC/management TLS is self-signed in this demo


def _base_search(range_key: str) -> str:
    """Common SPL for web_app_logs within the requested time window."""
    earliest = RANGE_MAP.get(range_key, "-15m")
    return f'search index=* sourcetype="web_app_logs" earliest={earliest} | spath'


def run_search(spl: str, config: SplunkConfig) -> list[dict]:
    """Execute a blocking export search and parse NDJSON results."""
    url = f"{config.url.rstrip('/')}/services/search/jobs/export"
    response = requests.post(
        url,
        auth=(config.user, config.password),
        data={"search": spl, "output_mode": "json"},
        verify=config.verify_ssl,
        timeout=30,
    )
    response.raise_for_status()

    results = []
    for line in response.text.strip().splitlines():
        if not line:
            continue
        try:
            row = json.loads(line)
            if "result" in row:
                results.append(row["result"])
        except json.JSONDecodeError:
            continue
    return results


def _format_recent_event(row: dict) -> dict:
    """Normalize a Splunk result row into the frontend event shape."""
    sc = row.get("status_code", 0)
    if isinstance(sc, list):
        sc = sc[0] if sc else 0

    raw = row.get("_raw", "")
    parsed_raw: dict = {}
    if raw:
        try:
            parsed_raw = json.loads(raw)
        except json.JSONDecodeError:
            parsed_raw = {}

    return {
        "timestamp": row.get("_time", row.get("timestamp", "")),
        "endpoint": row.get("endpoint", ""),
        "method": row.get("method", ""),
        "status_code": int(sc or 0),
        "response_time_ms": int(float(row.get("response_time_ms", 0) or 0)),
        "ip": row.get("ip", ""),
        "user_id": row.get("user_id", ""),
        "service": row.get("service", ""),
        "raw": raw,
        "parsed": parsed_raw,
        "splunk": {
            key: row.get(key, "")
            for key in ("_time", "host", "source", "sourcetype", "index", "_cd", "_indextime")
            if row.get(key)
        },
    }


def fetch_dashboard_data(range_key: str, config: SplunkConfig) -> dict:
    """Run all dashboard SPL queries in parallel and assemble the API payload."""
    base = _base_search(range_key)
    queries = {
        "summary": (
            f"{base} | stats count as total, "
            "avg(response_time_ms) as avg_latency, "
            "count(eval(tonumber(mvindex(status_code,0))>=400)) as errors, "
            'count(eval(endpoint="/login" AND tonumber(mvindex(status_code,0))=401)) as failed_logins'
        ),
        "by_endpoint": f"{base} | stats count by endpoint",
        "latency": (
            f"{base} | eval rt=tonumber(mvindex(response_time_ms,0)) "
            "| stats avg(rt) as avg_ms by endpoint"
        ),
        "timeline": f"{base} | timechart span=1m count",
        "status_by_endpoint": (
            f"{base} | eval sc=tonumber(mvindex(status_code,0)) "
            "| stats count by endpoint, sc"
        ),
        "recent": f"{base} | sort -_time | head 50",
    }

    data: dict[str, list[dict]] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(run_search, spl, config): name for name, spl in queries.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                data[name] = future.result()
            except Exception as exc:
                data[name] = []
                errors.append(f"{name}: {exc}")

    summary_row = data.get("summary", [{}])[0] if data.get("summary") else {}
    total = int(summary_row.get("total", 0) or 0)
    errors_count = int(summary_row.get("errors", 0) or 0)
    avg_latency = float(summary_row.get("avg_latency", 0) or 0)
    failed_logins = int(summary_row.get("failed_logins", 0) or 0)
    error_rate = (errors_count / total * 100) if total > 0 else 0.0

    recent = [_format_recent_event(row) for row in data.get("recent", [])]

    return {
        "ok": len(errors) == 0,
        "error": "; ".join(errors) if errors else None,
        "range": range_key,
        "summary": {
            "total": total,
            "error_rate": round(error_rate, 2),
            "avg_latency": round(avg_latency, 1),
            "failed_logins": failed_logins,
        },
        "by_endpoint": [
            {"endpoint": r.get("endpoint", "unknown"), "count": int(r.get("count", 0))}
            for r in data.get("by_endpoint", [])
        ],
        "latency": [
            {
                "endpoint": r.get("endpoint", "unknown"),
                "avg_ms": round(float(r.get("avg_ms", 0) or 0), 1),
            }
            for r in data.get("latency", [])
        ],
        "timeline": [
            {"time": r.get("_time", ""), "count": int(r.get("count", 0))}
            for r in data.get("timeline", [])
        ],
        "status_by_endpoint": [
            {
                "endpoint": r.get("endpoint", "unknown"),
                "status_code": int(r.get("sc", 0) or 0),
                "count": int(r.get("count", 0)),
            }
            for r in data.get("status_by_endpoint", [])
        ],
        "recent": recent,
    }
