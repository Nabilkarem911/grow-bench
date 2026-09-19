#!/bin/sh
# موجه المهام: بينفذ السكربت المكتوب في task.txt (عشان ما نغيّرش أمر الكومبوز تاني)
T=$(cat /app/task.txt 2>/dev/null | tr -d ' \r\n')
[ -z "$T" ] && T="run_arena.sh"
exec sh "/app/$T"
