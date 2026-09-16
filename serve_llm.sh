#!/bin/sh
# serve_llm.sh — يشغّل llama-server على السيرفر (موديل Qwen3-4B — 2.3 جيجا، آمن للإنتاج)
# بيدّي واجهة متوافقة مع OpenAI على المنفذ 8080 + صفحة محادثة جاهزة.
(apt-get update -qq && apt-get install -y -qq libgomp1 libstdc++6 ca-certificates >/dev/null 2>&1) || true

D=/data/llama
SRV=$(find "$D" -name "llama-server" -type f 2>/dev/null | head -1)
echo "خدمة الموديل: $SRV"
export LD_LIBRARY_PATH="$(dirname "$SRV"):$D:$LD_LIBRARY_PATH"
"$SRV" --help >/dev/null 2>&1 && echo "الأداة شغالة ✓" || echo "⚠️ مشكلة في الأداة"

M=/data/moe/Qwen3-4B-Q4_K_M.gguf
[ -s "$M" ] || { echo "❌ الموديل مش موجود: $M"; exit 1; }
echo "الموديل: $(du -h "$M" | cut -f1) · الرام المتاحة: $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) ميجا"

# --api-key إلزامي (الخدمة مكشوفة) — -t 3 لطيف على السيرفر الإنتاجي
exec "$SRV" \
  -m "$M" \
  -ngl 0 \
  -t 3 \
  -c 4096 \
  -nr \
  --no-warmup \
  --host 0.0.0.0 \
  --port 8080 \
  --api-key "${LLM_API_KEY:-orcanox-local-key}"
