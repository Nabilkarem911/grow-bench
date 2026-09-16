#!/bin/sh
# moe_bench_server.sh v2 — قياس موديل 30B على معالج السيرفر (بدون كارت شاشة).
# بنستخدم النسخة الخفيفة IQ2_M (9.7 جيجا) عشان تسع في رام السيرفر المتاحة (~12.7).
R=/data/results
mkdir -p "$R"
LOG="$R/moe_server.json"
exec >> "$LOG" 2>&1
echo ""
echo "=== بداية $(date -u) ==="
echo "موارد: أنوية=$(nproc) · متاح=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) ميجا · قرص /data فاضي=$(df -BG /data 2>/dev/null | awk 'NR==2{print $4}')"

# 0) مكتبات النظام المطلوبة لنسخة لينكس
(apt-get update -qq && apt-get install -y -qq libgomp1 curl >/dev/null 2>&1) || echo "تحذير: تعذّر تثبيت مكتبات النظام"

# 1) llama.cpp (نسخة لينكس)
TAG=b10988
D=/data/llama
mkdir -p "$D"
if [ ! -x "$D/llama-bench" ] || [ ! -x "$D/llama-cli" ]; then
  echo "بنزّل llama.cpp (نسخة لينكس)..."
  ok=0
  for try in 1 2 3 4 5; do
    curl -sL --max-time 900 -o /tmp/l.tar.gz "https://github.com/ggml-org/llama.cpp/releases/download/$TAG/llama-$TAG-bin-ubuntu-x64.tar.gz"
    SZ=$(wc -c < /tmp/l.tar.gz 2>/dev/null || echo 0)
    echo "  محاولة $try: $SZ بايت"
    if [ "$SZ" -gt 8000000 ]; then ok=1; break; fi
    sleep 5
  done
  if [ "$ok" != "1" ]; then echo "❌ تحميل llama.cpp فشل"; exit 1; fi
  tar xzf /tmp/l.tar.gz -C "$D" --strip-components=1 || { echo "❌ فك الضغط فشل"; exit 1; }
  chmod +x "$D"/llama-* 2>/dev/null
fi
ls -la "$D/llama-bench" "$D/llama-cli" 2>/dev/null || { echo "❌ الملفات التنفيذية مش موجودة"; exit 1; }
"$D/llama-bench" --version 2>&1 | head -2

# 2) الموديل الخفيف (9.7 جيجا)
M=/data/moe/Qwen3-30B-A3B-IQ2_M.gguf
mkdir -p /data/moe
for try in 1 2 3 4 5 6 7 8; do
  SZ=$(wc -c < "$M" 2>/dev/null || echo 0)
  if [ "$SZ" -gt 9500000000 ]; then break; fi
  echo "  تنزيل الموديل (محاولة $try) — الحالي: $((SZ/1048576)) ميجا"
  curl -sL -C - --max-time 2400 -o "$M" "https://huggingface.co/bartowski/Qwen_Qwen3-30B-A3B-GGUF/resolve/main/Qwen_Qwen3-30B-A3B-IQ2_M.gguf"
done
SZ=$(wc -c < "$M" 2>/dev/null || echo 0)
echo "حجم الموديل النهائي: $((SZ/1048576)) ميجا"
if [ "$SZ" -lt 9500000000 ]; then echo "❌ التنزيل مكتملش"; exit 1; fi

# 3) القياس
echo "===== قياس 4 أنوية (إمكانيات السيرفر الحقيقية) ====="
"$D/llama-bench" -m "$M" -ngl 0 -t 4 -p 32 -n 32 -r 3 -o md 2>&1 | tail -12

echo "===== توليد عربي حقيقي ====="
"$D/llama-cli" -m "$M" -ngl 0 -t 4 -c 2048 -nr -n 60 -st --no-warmup \
  -p "اكتب فقرة قصيرة عن أهمية التغليف الجيد للمطاعم. /no_think" 2>&1 | grep -aE "Generation:|Prompt:|التغليف|أهمية|الجيد" | tail -8
echo "=== خلص $(date -u) ==="
