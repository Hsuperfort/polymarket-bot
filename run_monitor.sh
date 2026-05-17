#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/monitor.log"

if [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
elif [ -f "/Users/hector/Library/Python/3.9/bin/python3" ]; then
    PYTHON="/Users/hector/Library/Python/3.9/bin/python3"
else
    PYTHON=$(which python3)
fi

mkdir -p "$SCRIPT_DIR/logs"
echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$LOG"
cd "$SCRIPT_DIR" && $PYTHON monitor.py >> "$LOG" 2>&1
