"""Custom web dashboard API — serves the UI and proxies metrics from Splunk REST."""

from pathlib import Path
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from splunk_search import SplunkConfig, fetch_dashboard_data, normalize_splunk_url

app = FastAPI(title="Splunk Web Dashboard")

STATIC_DIR = Path(__file__).parent / "static"

# Returned when Splunk is unreachable so the UI still renders empty panels.
EMPTY_DASHBOARD = {
    "summary": {"total": 0, "error_rate": 0, "avg_latency": 0, "failed_logins": 0},
    "by_endpoint": [],
    "latency": [],
    "timeline": [],
    "status_by_endpoint": [],
    "recent": [],
}


class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    """Disable browser caching for HTML/JS so dashboard updates deploy cleanly."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith(".html") or path.endswith(".js"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


app.add_middleware(NoCacheHTMLMiddleware)


class DashboardRequest(BaseModel):
    """Time window for dashboard queries: 15m, 1h, or 24h."""

    range: str = "15m"


def get_splunk_config() -> SplunkConfig:
    """Build Splunk REST credentials from environment variables."""
    url = os.getenv("SPLUNK_URL", "https://splunk:8089")
    user = os.getenv("SPLUNK_USER", "admin")
    password = os.getenv("SPLUNK_PASSWORD", "")
    if not password:
        raise RuntimeError(
            "SPLUNK_PASSWORD is not set. Add it to .env (see .env.example)."
        )
    return SplunkConfig(
        url=normalize_splunk_url(url),
        user=user.strip(),
        password=password,
    )


@app.get("/health")
def health():
    """Liveness probe for Docker."""
    return {"status": "ok"}


@app.post("/api/dashboard")
def dashboard(body: DashboardRequest):
    """Fetch KPIs, charts, and recent events for the selected time range."""
    range_key = body.range if body.range in ("15m", "1h", "24h") else "15m"
    try:
        return fetch_dashboard_data(range_key, get_splunk_config())
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "range": range_key,
            **EMPTY_DASHBOARD,
        }


@app.get("/")
def index():
    """Serve the dashboard single-page UI."""
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
