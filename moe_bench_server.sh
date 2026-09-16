#!/bin/sh
# moe_bench_server.sh v3 — نفس الهدف + تشخيص واختيار ذكي لملف llama.cpp التنفيذي
R=/data/results
mkdir -p "$R"
LOG="$R/moe_server.json"
exec >> "$LOG" 2>&1
echo ""
echo "=== بداية $(date -u) ==="
echo "موارد: أنوية=$(nproc) · متاح=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) ميجا · قرص=$(df -BG /data 2>/dev/null | awk 'NR==2{print $4}')"

D=/data/llama
mkdir -p "$D"
TAG=b10988
NEED_DL=0
[ -x "$D/llama-bench" ] || NEED_DL=1
if [ "$NEED_DL" = "1" ] || [ ! -s "$D/llama-cli" ]; then
  echo "بنزّل llama.cpp..."
  for try in 1 2 3 4 5; do
    curl -sL --max-time 900 -o /tmp/l.tar.gz "https://github.com/ggml-org/llama.cpp/releases/download/$TAG/llama-$TAG-bin-ubuntu-x64.tar.gz"
    SZ=$(wc -c < /tmp/l.tar.gz 2>/dev/null || echo 0)
    echo "  محاولة $try: $SZ بايت"
    [ "$SZ" -gt 8000000 ] && break
    sleep 5
  done
  rm -rf "$D"; mkdir -p "$D"
  tar xzf /tmp/l.tar.gz -C "$D" || { echo "فك الضغط فشل"; exit 1; }
  chmod -R +x "$D" 2>/dev/null
fi

echo "=== شجرة /data/llama (أول 25) ==="
ls -la "$D" | head -25
echo "=== بصمة أول 16 بايت من llama-bench (لازم تبدأ بـ 177 E L F) ==="
head -c 16 "$D/llama-bench" 2>/dev/null | od -c | head -2
echo "=== معمارية السيرفر ==="
uname -m
echo "=== ملفات .so ==="
find "$D" -name "*.so*" 2>/dev/null | head -8

# اختيار ملف llama-bench التنفيذي الصالح (بندور في أي مكان + نجرب مع مكتبات)
BENCH=""
for P in "$D/llama-bench" "$D/build/bin/llama-bench" "$D/bin/llama-bench" $(find "$D" -name "llama-bench" -type f 2>/dev/null); do
  [ -f "$P" ] || continue
  SZ=$(wc -c < "$P")
  if LD_LIBRARY_PATH="$D:$D/lib:$D/build/bin:$LD_LIBRARY_PATH" "$P" --version >/tmp/v.txt 2>&1; then
    echo "✅ ملف صالح: $P (حجم $SZ)"; head -2 /tmp/v.txt; BENCH="$P"; break
  else
    echo "❌ فشل: $P (حجم $SZ) → $(head -1 /tmp/v.txt)"
  fi
done

M=/data/moe/Qwen3-30B-A3B-IQ2_M.gguf
SZ=$(wc -c < "$M" 2>/dev/null || echo 0)
echo "حجم الموديل: $((SZ/1048576)) ميجا"

if [ -z "$BENCH" ]; then
  echo "❌ مفيش ملف llama تنفيذي صالح — نوقف عند التشخيص"
  exit 1
fi

export LD_LIBRARY_PATH="$D:$D/lib:$D/build/bin:$LD_LIBRARY_PATH"
echo "===== قياس 4 أنوية ====="
"$BENCH" -m "$M" -ngl 0 -t 4 -p 32 -n 32 -r 3 -o md 2>&1 | tail -12

echo "===== توليد عربي حقيقي ====="
CLI=$(dirname "$BENCH")/llama-cli
[ -f "$CLI" ] || CLI="$D/llama-cli"
"$CLI" -m "$M" -ngl 0 -t 4 -c 2048 -nr -n 60 -st --no-warmup \
  -p "اكتب فقرة قصيرة عن أهمية التغليف الجيد للمطاعم. /no_think" 2>&1 | grep -aE "Generation:|Prompt:|التغليف|أهمية|الجيد" | tail -8
echo "=== خلص $(date -u) ==="
