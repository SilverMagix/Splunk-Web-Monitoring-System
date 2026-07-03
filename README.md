# Splunk Web Monitoring System

A minimal end-to-end observability demo: a simulated FastAPI web API, a monitoring service that forwards structured logs to Splunk HEC, and a load generator that simulates realistic traffic patterns.

Splunk is the primary dashboard for monitoring.

## Architecture

```
Load Generator
      ↓
Web App (FastAPI)          :8001
      ↓ logs (POST /ingest)
Monitoring Service         :8002
      ↓ HEC
Splunk                     :8000 (UI), :8088 (HEC)
      ↓
Search + Dashboard (Splunk UI)
```

## Prerequisites

- Docker and Docker Compose
- ~4 GB RAM for Splunk container

## Quick Start

### 1. Start Splunk

```bash
docker compose up splunk -d
```

Wait 2–3 minutes for Splunk to finish starting.

### 2. Enable HEC and create a token

1. Open http://localhost:8000
2. Login: `admin` / `Password123!`
3. Go to **Settings → Data Inputs → HTTP Event Collector → Global Settings**
4. Enable HTTP Event Collector
5. Click **New Token**
   - Name: `web-app-monitoring`
   - Source type: `web_app_logs` (or leave default and let the payload sourcetype apply)
6. Copy the generated token

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set SPLUNK_TOKEN to your HEC token
```

### 4. Start all services

```bash
docker compose up -d
```

### 5. Generate traffic

```bash
docker compose --profile load up load-generator
```

Or run the load generator locally:

```bash
cd load-generator
pip install -r requirements.txt
WEB_APP_URL=http://localhost:8001 python generator.py
```

### 6. Verify logs in Splunk

In Splunk Search, run:

```spl
index=* sourcetype="web_app_logs" | head 20
```

## Local Development (without Docker for app services)

Terminal 1 — monitoring service:

```bash
cd monitoring-service
pip install -r requirements.txt
export SPLUNK_HEC_URL=http://localhost:8088/services/collector
export SPLUNK_TOKEN=your-token
uvicorn main:app --host 0.0.0.0 --port 8002
```

Terminal 2 — web app:

```bash
cd web-app
pip install -r requirements.txt
export MONITORING_SERVICE_URL=http://localhost:8002
uvicorn main:app --host 0.0.0.0 --port 8001
```

Terminal 3 — load generator:

```bash
cd load-generator
pip install -r requirements.txt
WEB_APP_URL=http://localhost:8001 python generator.py
```

## API Endpoints

| Endpoint    | Method | Behavior                                      |
|-------------|--------|-----------------------------------------------|
| `/health`   | GET    | Instant health check                          |
| `/products` | GET    | 20–100 ms delay, returns fake product list    |
| `/login`    | POST   | 70% success (200), 30% failure (401)          |
| `/checkout` | POST   | 200–1500 ms delay, ~15% server error (500)    |

Every request generates a structured log:

```json
{
  "timestamp": "2026-07-03T15:46:00.123456+00:00",
  "service": "web-app",
  "endpoint": "/login",
  "method": "POST",
  "status_code": 401,
  "response_time_ms": 87,
  "ip": "203.0.113.42",
  "user_id": "user_1234"
}
```

Logs are sent to the monitoring service, which forwards them to Splunk via HEC. If Splunk is unavailable, the application continues running without errors.

## Splunk Dashboard Queries

Create a dashboard in Splunk UI and add panels with these searches. Set refresh to 30 seconds.

### Total requests

```spl
index=* sourcetype="web_app_logs"
| stats count
```

### Requests per endpoint

```spl
index=* sourcetype="web_app_logs"
| stats count by event.endpoint
```

### Error rate

```spl
index=* sourcetype="web_app_logs"
| stats count(eval(event.status_code>=400)) as errors, count as total
| eval error_rate = (errors/total)*100
```

### Latency average by endpoint

```spl
index=* sourcetype="web_app_logs"
| stats avg(event.response_time_ms) by event.endpoint
```

### Failed logins

```spl
index=* sourcetype="web_app_logs"
event.endpoint="/login" AND event.status_code=401
```

## Load Generator Behavior

- **Baseline:** random endpoint every 200–500 ms (weighted: products 40%, login 30%, checkout 20%, health 10%)
- **Burst:** every 10 seconds, fires 10–20 rapid requests
- **Brute force:** every 30 seconds, 5–10 consecutive failed login attempts
- **Checkout spike:** every 45 seconds, 3–5 concurrent checkout requests

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No events in Splunk | Confirm HEC is enabled and `SPLUNK_TOKEN` in `.env` is correct |
| `401` from Splunk HEC | Token is invalid or expired — create a new one |
| Web app works but no Splunk data | Check monitoring-service logs: `docker compose logs monitoring-service` |
| Splunk container won't start | Ensure ports 8000 and 8088 are free; allow 2–3 min for first boot |
| App crashes when Splunk is down | Should not happen — Splunk failures are swallowed silently |

## Project Structure

```
├── docker-compose.yml
├── .env.example
├── web-app/              # Simulated API
├── monitoring-service/   # Log ingest + Splunk HEC forwarder
└── load-generator/       # Traffic simulator
```
