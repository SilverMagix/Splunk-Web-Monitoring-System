"""Log ingest service: accepts structured web-app events and ships them to Splunk."""

from fastapi import FastAPI
from pydantic import BaseModel

from splunk_client import send_to_splunk

app = FastAPI(title="Monitoring Service")


class LogEvent(BaseModel):
    """Schema for request logs produced by the web-app middleware."""

    timestamp: str
    service: str
    endpoint: str
    method: str
    status_code: int
    response_time_ms: int
    ip: str
    user_id: str | None = None


@app.get("/health")
def health():
    """Liveness probe for Docker."""
    return {"status": "ok"}


@app.post("/ingest")
def ingest(event: LogEvent):
    """Accept one log event and forward it to Splunk."""
    send_to_splunk(event.model_dump(exclude_none=True))
    return {"status": "accepted"}
