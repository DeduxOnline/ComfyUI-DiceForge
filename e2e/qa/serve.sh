#!/usr/bin/env bash
# The e2e ComfyUI server (server.js: test models, wildcards and stand-ins for Civitai and Danbooru, nothing online) in the background, for the
# QA tools: e2e/qa/serve.sh start | stop | status. Its log: e2e/qa/out/server.log.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${DICEFORGE_E2E_PORT:-8199}"
LOG=qa/out/server.log
PID=qa/out/server.pid
ready() { curl -sf -o /dev/null "http://127.0.0.1:$PORT/object_info/DiceForgeLoraStack"; }

case "${1:-start}" in
  start)
    if ready; then echo "Running: http://127.0.0.1:$PORT"; exit 0; fi
    mkdir -p qa/out
    nohup node server.js > "$LOG" 2>&1 &
    echo $! > "$PID"
    for _ in $(seq 1 120); do
      if ready; then echo "Ready: http://127.0.0.1:$PORT (log: e2e/$LOG)"; exit 0; fi
      sleep 2
    done
    echo "The server did not start; the end of e2e/$LOG:"
    tail -20 "$LOG"
    exit 1
    ;;
  stop)
    if [[ -f "$PID" ]]; then kill "$(cat "$PID")" 2>/dev/null || true; rm -f "$PID"; fi
    echo "Stopped."
    ;;
  status)
    if ready; then echo "Running: http://127.0.0.1:$PORT"; else echo "Not running."; fi
    ;;
  *)
    echo "Usage: e2e/qa/serve.sh start | stop | status"
    exit 2
    ;;
esac
