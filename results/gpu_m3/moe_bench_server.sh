#!/bin/sh
# moe_bench_server.sh — قياس الموديل الكبير على معالج السيرفر (بدون كارت شاشة).
# ملاحظة: السيرفر فاضي ~12.7 جيجا والموديل 17.3 → جزء هيقرا من القرص. ده اللي بنقيسه.
R=/data/results
mkdir -p "$R"
LOG="$R/moe_server.json"
exec >> "$LOG" 2>&1
echo "=== بداية $(date -u) ==="
echo "موارد: $(nproc) أنوية · متاح $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) ميجا · قرص /data فاضي $(df -BG /data 2>/dev/null | awk 'NR==2{print $4}')"

TAG=b10988
D=/data/llama
mkdir -p "$D"
if [ ! -x "$D/llama-bench" ]; then
  echo "بنزّل llama.cpp (نسخة لينكس)..."
  curl -sL --max-time 900 -o /tmp/l.tar.gz "https://github.com/ggml-org/llama.cpp/releases/download/$TAG/llama-$TAG-bin-ubuntu-x64.tar.gz"
  SZ=$(wc -c < /tmp/l.tar.gz 2>/dev/null || echo 0)
  echo "حجم الملف المنزّل: $SZ بايت"
  if [ "$SZ" -lt 5000000 ]; then echo "❌ التحميل ناقص — نوقف"; exit 1; fi
  tar xzf /tmp/l.tar.gz -C "$D" --strip-components=1 || { echo "❌ فك الضغط فشل"; exit 1; }
  chmod +x "$D"/llama-* 2>/dev/null
fi
ls -la "$D/llama-bench" 2>/dev/null || { echo "❌ الملف التنفيذي مش موجود"; exit 1; }

M=/data/moe/Qwen3-30B-A3B-Q4_K_M.gguf
mkdir -p /data/moe
if [ ! -s "$M" ] || [ "$(wc -c < "$M")" -lt 10000000000 ]; then
  echo "بنزّل الموديل (17 جيجا)..."
  curl -sL -C - --max-time 10800 -o "$M" "https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/resolve/main/Qwen3-30B-A3B-Q4_K_M.gguf"
fi
echo "حجم الموديل: $(du -h "$M" 2>/dev/null | cut -f1)"

echo "===== قياس ٤ أنوية (زي إمكانيات السيرفر) ====="
"$D/llama-bench" -m "$M" -ngl 0 -t 4 -c 2048 -p 32 -n 32 -r 1 -o md 2>&1 | tail -10

echo "===== توليد عربي حقيقي ====="
"$D/llama-cli" -m "$M" -ngl 0 -t 4 -c 2048 -n 50 -st --no-warmup \
  -p "اكتب فقرة قصيرة عن أهمية التغليف الجيد للمطاعم. /no_think" 2>&1 | grep -aE "Generation:|Prompt:|التغليف|أهمية|^[^>=/]" | tail -10
echo "=== خلص $(date -u) ==="
