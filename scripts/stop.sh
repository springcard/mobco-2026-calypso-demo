#!/bin/bash
PIDDIR=home/springcard/pid
for f in "$PIDDIR"/*.pid; do
    [ -f "$f" ] || continue
    PID=$(cat "$f")
    echo "Stopping PID $PID from $f"
    kill "$PID" 2>/dev/null
    rm -f "$f"
done
