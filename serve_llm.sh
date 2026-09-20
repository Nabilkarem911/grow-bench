#!/bin/sh
# serve_llm.sh — يشغّل llama-server على السيرفر (موديل Qwen3-4B — 2.3 جيجا، آمن للإنتاج)
# بيدّي واجهة متوافقة مع OpenAI على المنفذ 8080 + صفحة محادثة جاهزة.
(apt-get update -qq && apt-get install -y -qq libgomp1 libstdc++6 ca-certificates >/dev/null 2>&1) || true

D=/data/llama
SRV=$(find "$D" -name "llama-server" -type f 2>/dev/null | head -1)
echo "خدمة الموديل: $SRV"
export LD_LIBRARY_PATH="$(dirname "$SRV"):$D:$LD_LIBRARY_PATH"
"$SRV" --help >/dev/null 2>&1 && echo "الأداة شغالة ✓" || echo "⚠️ مشكلة في الأداة"

M=${LLM_MODEL:-/data/moe/exp4.gguf}
if [ ! -s "$M" ]; then
  echo "⬇️ الموديل مش موجود — بننزّله: $M"
  mkdir -p "$(dirname "$M")"
  python3 - "$M" <<'PY' || { echo "❌ فشل التنزيل"; sleep 900; }
import os, sys, urllib.request
dst = sys.argv[1]
name = os.path.basename(dst)
# نفس المستودع اللي نزّلنا منه قبل كده
url = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/" + name
if "1.7B" in name:
    url = "https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/main/" + name
if "8B" in name:
    url = "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/" + name
pos = os.path.getsize(dst) if os.path.exists(dst) else 0
hdr = {"Range": "bytes=%d-" % pos} if pos else {}
print("بنزّل:", url, flush=True)
with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=3600) as r, open(dst, "ab" if pos else "wb") as f:
    while True:
        ch = r.read(1 << 20)
        if not ch:
            break
        f.write(ch)
print("✅ اتنزّل:", round(os.path.getsize(dst) / 2**20), "ميجا")
PY
fi
[ -s "$M" ] || { echo "❌ الموديل مش موجود: $M"; exit 1; }
echo "الموديل: $(du -h "$M" | cut -f1) · الرام المتاحة: $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) ميجا"

# --api-key إلزامي (الخدمة مكشوفة) — -t 3 لطيف على السيرفر الإنتاجي
# -rea off: نلغي «التفكير» — كان بيرد بالصيني في مرحلة التفكير وبيبطّئ الرد
exec "$SRV" \
  -m "$M" \
  -ngl 0 \
  -t 3 \
  -c 4096 \
  -nr \
  -rea off \
  --repeat-penalty 1.15 \
  --repeat-last-n 128 \
  --no-warmup \
  --host 0.0.0.0 \
  --port 8080 \
  --api-key "${LLM_API_KEY:-orcanox-local-key}"
