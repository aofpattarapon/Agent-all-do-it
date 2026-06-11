#!/usr/bin/env bash
# Run Celery worker + beat natively on Mac so claude-cli agents work.
# Usage: ./run-workers.sh
#        ./run-workers.sh stop
# Logs: logs/celery-worker.log, logs/celery-beat.log

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
LOGS="$ROOT/logs"
PIDFILE_WORKER="$LOGS/celery-worker.pid"
PIDFILE_BEAT="$LOGS/celery-beat.pid"

mkdir -p "$LOGS"

stop_workers() {
    for pid_file in "$PIDFILE_WORKER" "$PIDFILE_BEAT"; do
        if [[ -f "$pid_file" ]]; then
            pid=$(cat "$pid_file")
            if kill -0 "$pid" 2>/dev/null; then
                echo "Stopping PID $pid..."
                kill "$pid"
            fi
            rm -f "$pid_file"
        fi
    done
    echo "Workers stopped."
}

if [[ "${1:-}" == "stop" ]]; then
    stop_workers
    exit 0
fi

stop_workers 2>/dev/null || true

cd "$BACKEND"

echo "Starting Celery worker..."
uv run python -m celery -A app.worker.celery_app worker \
    --loglevel=info >> "$LOGS/celery-worker.log" 2>&1 &
WORKER_PID=$!
echo $WORKER_PID > "$PIDFILE_WORKER"

echo "Starting Celery beat..."
uv run python -m celery -A app.worker.celery_app beat \
    --loglevel=info >> "$LOGS/celery-beat.log" 2>&1 &
BEAT_PID=$!
echo $BEAT_PID > "$PIDFILE_BEAT"

echo ""
echo "Workers running."
echo "  Worker PID : $WORKER_PID  (logs/celery-worker.log)"
echo "  Beat PID   : $BEAT_PID  (logs/celery-beat.log)"
echo ""
echo "Tail logs:  tail -f $LOGS/celery-worker.log"
echo "Stop:       ./run-workers.sh stop"
