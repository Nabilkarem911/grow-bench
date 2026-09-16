#!/bin/sh
# exp_experts.sh — تجربة «الحمية من الخبراء» + موديل صغير ذكي، على معالج السيرفر (ARM64، بدون كارت).
# بيقيس: 8 خبراء (الأصلي) · 4 خبراء · 2 خبراء · وموديل Qwen3-4B (صغير وذكي)
R=/data/results
mkdir -p "$R"
LOG="$R/moe_experts.json"
(apt-get update -qq && apt-get install -y -qq curl ca-certificates libgomp1 libstdc++6 >/dev/null 2>&1) || true
exec >> "$LOG" 2>&1
echo ""
echo "=== بداية $(date -u) ==="
echo "موارد: أنوية=$(nproc) · متاح=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) ميجا · قرص=$(df -BG /data | awk 'NR==2{print $4}')"

D=/data/llama
BENCH=$(find "$D" -name llama-bench -type f 2>/dev/null | head -1)
CLI=$(find "$D" -name llama-cli -type f 2>/dev/null | head -1)
export LD_LIBRARY_PATH="$(dirname "$BENCH"):$D:$LD_LIBRARY_PATH"
echo "الأدوات: $BENCH"
"$BENCH" --help >/dev/null 2>&1 && echo "الأداة شغالة ✓" || echo "⚠️ الأداة فيها مشكلة"

BASE=/data/moe/Qwen3-30B-A3B-IQ2_M.gguf
P="اكتب فقرة قصيرة عن أهمية التغليف الجيد للمطاعم. /no_think"
Q=/data/moe/Qwen3-4B-Q4_K_M.gguf

run_bench() {
  echo "----- $2 -----"
  "$BENCH" -m "$1" -ngl 0 -t 4 -p 32 -n 32 -r 1 -o md 2>&1 | grep -aE "^\| qwen|error" | tail -3
}

run_gen() {
  "$CLI" -m "$1" -ngl 0 -t 4 -c 2048 -nr -st --no-warmup -n 60 -p "$P" 2>&1 \
    | grep -avE "^>|^=|^/|commands|Loading|^model |^ftype|^modalit|^build|^available|^system|^llama_|^ggml_|^load_|^print_|^init:|^srv |^\s*$" | tail -6
}

echo ""
echo "########## ١) الأساس: 8 خبراء (الأصلي) ##########"
run_bench "$BASE" "8 خبراء — السرعة"

echo ""
echo "########## ٢) 4 خبراء ##########"
python3 /app/patch_experts.py "$BASE" /data/moe/exp4.gguf 4
run_bench /data/moe/exp4.gguf "4 خبراء — السرعة"

echo ""
echo "########## ٣) 2 خبراء ##########"
python3 /app/patch_experts.py "$BASE" /data/moe/exp2.gguf 2
run_bench /data/moe/exp2.gguf "2 خبراء — السرعة"

echo ""
echo "########## ٤) الموديل الصغير الذكي: Qwen3-4B ##########"
if [ ! -s "$Q" ] || [ "$(wc -c < "$Q" 2>/dev/null || echo 0)" -lt 2000000000 ]; then
  echo "بنزّله (2.3 جيجا)..."
  for i in 1 2 3 4 5; do
    curl -sL -C - --max-time 1500 -o "$Q" "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"
    SZ=$(wc -c < "$Q" 2>/dev/null || echo 0)
    echo "  محاولة $i: $((SZ/1048576)) ميجا"
    [ "$SZ" -gt 2000000000 ] && break
    sleep 5
  done
fi
echo "حجم الصغير: $(du -h "$Q" 2>/dev/null | cut -f1)"
run_bench "$Q" "Qwen3-4B — السرعة"

echo ""
echo "########## ٥) جودة العربي: 4 خبراء ##########"
run_gen /data/moe/exp4.gguf

echo ""
echo "########## ٦) جودة العربي: Qwen3-4B ##########"
run_gen "$Q"

echo ""
echo "=== خلص $(date -u) ==="
