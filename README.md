# Splunk Web Monitoring System

A minimal end-to-end observability demo: a simulated FastAPI web API (with built-in load generator) and a monitoring service that forwards structured logs to Splunk HEC.

Splunk is the primary dashboard for monitoring. A custom web dashboard is also available at **http://localhost:8003**.

## Architecture

```
Web App (FastAPI + load generator)  :8001
      ↓ logs (POST /ingest)
Monitoring Service                  :8002
      ↓ HEC
Splunk                              :8342 (UI), :8088 (HEC)
      ↓
Web Dashboard                       :8003  (reads from Splunk REST API)
Splunk UI Search + Dashboard
```

## Prerequisites

- Docker and Docker Compose
- ~4 GB RAM for Splunk container
- Bash (for the demo script)

## Quick Start

```bash
git clone https://github.com/SilverMagix/Splunk-Web-Monitoring-System.git
cd Splunk-Web-Monitoring-System
./scripts/demo.sh
```

The script will:

1. Start Splunk and wait until it is ready
2. Enable HEC and create a token automatically (saved to `.env`)
3. Build and start all services (web-app with optional load generator, monitoring-service, dashboard)

When finished, open:

| Service | URL |
|---------|-----|
| Custom dashboard | http://localhost:8003 |
| Splunk UI | http://localhost:8342 (`admin` / `Password123!`) |
| Web API | http://localhost:8001 |

Stop everything:

```bash
./scripts/demo.sh --down
```

Other options:

```bash
./scripts/demo.sh --no-load   # start stack without load generator
./scripts/demo.sh --help
```

### Verify logs in Splunk

In Splunk Search, run:

```spl
index=* sourcetype="web_app_logs" | head 20
```

Or use the custom dashboard at http://localhost:8003 (auto-refreshes every 15 seconds).

The dashboard reads Splunk REST credentials from `.env`:

| Variable | Default |
|----------|---------|
| `SPLUNK_URL` | `https://splunk:8089` |
| `SPLUNK_USER` | `admin` |
| `SPLUNK_PASSWORD` | `Password123!` |

## Manual Setup (optional)

Use this if `./scripts/demo.sh` fails during HEC setup, or you prefer configuring Splunk yourself.

### 1. Start Splunk

```bash
docker compose up splunk -d
```

### 2. Enable HEC and create a token

1. Open http://localhost:8342
2. Login: `admin` / `Password123!`
3. Go to **Settings → Data Inputs → HTTP Event Collector → Global Settings**
4. Enable HTTP Event Collector
5. Click **New Token**
   - Name: `web-app-monitoring`
   - Source type: `web_app_logs`
6. Copy the generated token into `.env` as `SPLUNK_TOKEN`

### 3. Configure environment and start services

```bash
cp .env.example .env
# Edit .env: set SPLUNK_TOKEN and confirm SPLUNK_PASSWORD matches Splunk
docker compose up -d --build
```

## Local Development (without Docker for app services)

Terminal 1 — monitoring service:

```bash
cd monitoring-service
pip install -r requirements.txt
export SPLUNK_HEC_URL=https://localhost:8088/services/collector
export SPLUNK_TOKEN=your-token
uvicorn main:app --host 0.0.0.0 --port 8002
```

Terminal 2 — web app (and optional load generator):

```bash
cd web-app
pip install -r requirements.txt
export MONITORING_SERVICE_URL=http://localhost:8002
# Runs uvicorn + load generator (set ENABLE_LOAD_GENERATOR=false to skip)
./entrypoint.sh
```

Or run them separately:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
# other terminal:
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
| Demo script fails on HEC | Run `docker compose logs splunk --tail 30`; try manual HEC setup below |
| No events in Splunk | HEC requires **HTTPS** (`https://...:8088/services/collector`), not HTTP; confirm HEC is enabled and `SPLUNK_TOKEN` in `.env` is correct |
| `401` from Splunk HEC | Token is invalid or expired — create a new one |
| Web app works but no Splunk data | Check monitoring-service logs: `docker compose logs monitoring-service` |
| Splunk container won't start | Check `docker compose logs splunk` — newer images need `SPLUNK_GENERAL_TERMS`; ensure ports 8342 and 8088 are free; allow 2–3 min for first boot |
| App crashes when Splunk is down | Should not happen — Splunk failures are swallowed silently |
| Dashboard shows connection error | Check `SPLUNK_URL` / `SPLUNK_USER` / `SPLUNK_PASSWORD` in `.env`; Docker Compose default URL is `https://splunk:8089` |

## Project Structure

```
├── docker-compose.yml
├── .env.example
├── scripts/
│   └── demo.sh           # One-command demo launcher
├── web-app/              # Simulated API + load generator
├── monitoring-service/   # Log ingest + Splunk HEC forwarder
└── dashboard/            # Web UI (reads from Splunk REST API)
```
