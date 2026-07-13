#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPLUNK_USER="${SPLUNK_USER:-admin}"
SPLUNK_PASSWORD="${SPLUNK_PASSWORD:-Password123!}"
HEC_TOKEN_NAME="${HEC_TOKEN_NAME:-web-app-monitoring}"
SPLUNK_WAIT_SECONDS="${SPLUNK_WAIT_SECONDS:-300}"
HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-120}"

NO_LOAD=false

usage() {
  cat <<'EOF'
Usage: ./scripts/demo.sh [OPTIONS]

Start the full Splunk Web Monitoring demo (Splunk + HEC + services + load generator).

Options:
  --down      Stop all demo containers
  --no-load   Start stack without the load generator
  --help      Show this help message

Examples:
  ./scripts/demo.sh
  ./scripts/demo.sh --no-load
  ./scripts/demo.sh --down
EOF
}

log() { printf '==> %s\n' "$*" >&2; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

splunk_api() {
  docker compose exec -T splunk curl -sk -u "${SPLUNK_USER}:${SPLUNK_PASSWORD}" "$@"
}

parse_token_from_xml() {
  sed -n 's/.*<s:key name="token">\([^<]*\)<\/s:key>.*/\1/p' | head -1
}

get_env_value() {
  local key=$1
  if [[ -f .env ]] && grep -q "^${key}=" .env; then
    grep "^${key}=" .env | tail -1 | cut -d= -f2-
  fi
}

set_env_value() {
  local key=$1 value=$2
  local tmp
  touch .env
  tmp=$(mktemp)
  if grep -q "^${key}=" .env 2>/dev/null; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      if [[ "$line" == "${key}="* ]]; then
        printf '%s=%s\n' "$key" "$value"
      else
        printf '%s\n' "$line"
      fi
    done < .env > "$tmp"
  else
    cp .env "$tmp"
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  mv "$tmp" .env
}

token_is_placeholder() {
  local token=$1
  [[ -z "$token" || "$token" == "your-hec-token-here" ]]
}

verify_hec_token() {
  local token=$1
  [[ -n "$token" ]] || return 1
  local code
  code=$(curl -sk -o /dev/null -w '%{http_code}' \
    -H "Authorization: Splunk ${token}" \
    https://localhost:8088/services/collector/health 2>/dev/null || echo "000")
  [[ "$code" == "200" ]]
}

wait_for_splunk() {
  log "Waiting for Splunk to be ready (up to ${SPLUNK_WAIT_SECONDS}s)..."
  local elapsed=0
  while (( elapsed < SPLUNK_WAIT_SECONDS )); do
    if splunk_api https://localhost:8089/services/server/info >/dev/null 2>&1; then
      log "Splunk is ready"
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  die "Splunk did not become ready in time. Try: docker compose logs splunk --tail 30"
}

enable_hec() {
  log "Enabling HTTP Event Collector..."
  splunk_api -X POST "https://localhost:8089/services/data/inputs/http/http/enable" >/dev/null || true
}

fetch_existing_token() {
  local response
  response=$(splunk_api \
    "https://localhost:8089/servicesNS/admin/splunk_httpinput/data/inputs/http/${HEC_TOKEN_NAME}" 2>/dev/null || true)
  echo "$response" | parse_token_from_xml
}

create_hec_token() {
  log "Creating HEC token '${HEC_TOKEN_NAME}'..."
  local response
  response=$(splunk_api \
    -X POST "https://localhost:8089/servicesNS/admin/splunk_httpinput/data/inputs/http" \
    -d "name=${HEC_TOKEN_NAME}" \
    -d "index=main" \
    -d "sourcetype=web_app_logs")
  local token
  token=$(echo "$response" | parse_token_from_xml)
  if [[ -n "$token" ]]; then
    echo "$token"
    return 0
  fi

  warn "Token creation response did not include a token; trying to fetch existing token"
  fetch_existing_token
}

ensure_hec_token() {
  local existing
  existing=$(get_env_value SPLUNK_TOKEN)
  if ! token_is_placeholder "$existing" && verify_hec_token "$existing"; then
    log "Reusing existing HEC token from .env"
    echo "$existing"
    return 0
  fi

  enable_hec

  local token
  token=$(fetch_existing_token)
  if [[ -n "$token" ]]; then
    log "Using existing Splunk HEC token '${HEC_TOKEN_NAME}'"
    echo "$token"
    return 0
  fi

  token=$(create_hec_token)
  [[ -n "$token" ]] || die "Failed to create or fetch HEC token. See README manual setup section."
  echo "$token"
}

write_env_file() {
  local token=$1
  token=$(printf '%s' "$token" | grep -oE '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' | head -1)
  [[ -n "$token" ]] || die "Invalid HEC token (expected UUID)"
  if [[ ! -f .env ]]; then
    cp .env.example .env
  fi
  set_env_value SPLUNK_HEC_URL "https://splunk:8088/services/collector"
  set_env_value SPLUNK_TOKEN "$token"
  set_env_value SPLUNK_URL "https://splunk:8089"
  set_env_value SPLUNK_USER "${SPLUNK_USER}"
  set_env_value SPLUNK_PASSWORD "${SPLUNK_PASSWORD}"
  log "Updated .env with HEC and dashboard Splunk credentials"
}

wait_for_url() {
  local url=$1 name=$2
  local elapsed=0
  while (( elapsed < HEALTH_WAIT_SECONDS )); do
    if curl -sf "$url" >/dev/null 2>&1; then
      log "${name} is healthy"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "${name} did not become healthy at ${url}"
}

send_test_event() {
  curl -sf -X POST http://localhost:8002/ingest \
    -H "Content-Type: application/json" \
    -d '{"timestamp":"2026-01-01T00:00:00+00:00","service":"web-app","endpoint":"/health","method":"GET","status_code":200,"response_time_ms":1,"ip":"127.0.0.1"}' \
    >/dev/null || warn "Test ingest request failed (non-fatal)"
}

teardown() {
  log "Stopping demo containers..."
  docker compose down
  log "Demo stopped"
}

run_demo() {
  require_cmd docker
  docker compose version >/dev/null 2>&1 || die "docker compose is required"

  log "Starting Splunk..."
  docker compose up splunk -d

  wait_for_splunk

  local token
  token=$(ensure_hec_token)
  write_env_file "$token"

  if [[ "$NO_LOAD" == true ]]; then
    set_env_value ENABLE_LOAD_GENERATOR "false"
    log "Load generator disabled (ENABLE_LOAD_GENERATOR=false)"
  else
    set_env_value ENABLE_LOAD_GENERATOR "true"
  fi

  log "Building and starting application services..."
  docker compose up -d --build

  wait_for_url "http://localhost:8001/health" "Web app"
  wait_for_url "http://localhost:8002/health" "Monitoring service"
  wait_for_url "http://localhost:8003/health" "Dashboard"

  send_test_event

  cat <<EOF

Demo is running!

  Custom dashboard:  http://localhost:8003
  Splunk UI:         http://localhost:8342  (${SPLUNK_USER} / ${SPLUNK_PASSWORD})
  Web API:           http://localhost:8001

  HEC token saved to .env (not printed for security).

  Stop everything:   ./scripts/demo.sh --down
EOF

  if [[ "$NO_LOAD" == false ]]; then
    echo "  Load generator:    running inside web-app (docker compose logs -f web-app)"
  else
    echo "  Load generator:    disabled"
  fi
  echo
}

# Parse args
if [[ $# -eq 0 ]]; then
  run_demo
  exit 0
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --down)
      teardown
      exit 0
      ;;
    --no-load)
      NO_LOAD=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1 (try --help)"
      ;;
  esac
done

run_demo
