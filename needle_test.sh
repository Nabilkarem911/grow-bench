#!/bin/sh
T=$(cat /app/task.txt 2>/dev/null | tr -d " 
")
[ -z "$T" ] && T="run_arena.sh"
exec sh -c "$(sed "s/$//" "/app/$T")"
