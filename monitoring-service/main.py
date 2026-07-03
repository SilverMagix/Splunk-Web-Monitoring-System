from fastapi import FastAPI
from pydantic import BaseModel

from splunk_client import send_to_splunk

app = FastAPI(title="Monitoring Service")


class LogEvent(BaseModel):
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
    return {"status": "ok"}


@app.post("/ingest")
def ingest(event: LogEvent):
    send_to_splunk(event.model_dump(exclude_none=True))
    return {"status": "accepted"}
