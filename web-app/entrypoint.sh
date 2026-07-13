#!/bin/sh
set -e

uvicorn main:app --host 0.0.0.0 --port 8001 &
UVICORN_PID=$!

LOAD_PID=""
if [ "${ENABLE_LOAD_GENERATOR:-true}" = "true" ]; then
  export WEB_APP_URL="${WEB_APP_URL:-http://127.0.0.1:8001}"
  i=0
  while [ "$i" -lt 30 ]; do
    if python -c "import urllib.request; urllib.request.urlopen('${WEB_APP_URL}/health', timeout=1)" 2>/dev/null; then
      break
    fi
    i=$((i + 1))
    sleep 0.5
  done
  python -u generator.py &
  LOAD_PID=$!
fi

trap 'kill "$UVICORN_PID" $LOAD_PID 2>/dev/null; exit 0' TERM INT

wait "$UVICORN_PID"
STATUS=$?
kill $LOAD_PID 2>/dev/null || true
exit "$STATUS"
