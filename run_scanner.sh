#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/cron.log"

# Python : venv VPS en priorité, sinon Python local Mac
if [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
elif [ -f "/Users/hector/Library/Python/3.9/bin/python3" ]; then
    PYTHON="/Users/hector/Library/Python/3.9/bin/python3"
else
    PYTHON=$(which python3)
fi

mkdir -p "$SCRIPT_DIR/logs"
echo "--- $(date '+%Y-%m-%d %H:%M:%S') --- SCAN DÉMARRÉ ---" >> "$LOG"
cd "$SCRIPT_DIR" && $PYTHON scanner.py >> "$LOG" 2>&1
echo "--- $(date '+%Y-%m-%d %H:%M:%S') --- SCAN TERMINÉ ---" >> "$LOG"
