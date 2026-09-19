#!/bin/sh
# serve_embed.sh — خدمة تمثيل (embeddings) متعددة اللغات على llama.cpp
# الموديل: BAAI/bge-m3 (1024 بُعد · 100+ لغة · عربي متقدم)
M=${EMBED_MODEL:-/data/moe/bge-m3-f16.gguf}
URL=${EMBED_MODEL_URL:-https://huggingface.co/CompendiumLabs/bge-m3-gguf/resolve/main/bge-m3-f16.gguf}
BIN=/data/llama/llama-server

if [ ! -x "$BIN" ]; then
  echo "⚠️ llama-server مش موجود على السيرفر"
  sleep infinity
fi

if [ ! -f "$M" ]; then
  echo "⬇️ بنزّل موديل التمثيل (1.1 جيجا)..."
  python3 - "$URL" "$M" <<'PY' || { echo 'فشل التنزيل'; sleep infinity; }
import os, sys, urllib.request
url, dst = sys.argv[1], sys.argv[2]
pos = os.path.getsize(dst) if os.path.exists(dst) else 0
req = urllib.request.Request(url, headers={"Range": f"bytes={pos}-"} if pos else {})
with urllib.request.urlopen(req, timeout=1800) as r, open(dst, "ab" if pos else "wb") as f:
    while True:
        chunk = r.read(1 << 20)
        if not chunk: break
        f.write(chunk)
print("✅ اتنزّل:", round(os.path.getsize(dst)/2**20), "ميجا")
PY
fi

echo "🚀 تشغيل خدمة التمثيل على 8080"
exec "$BIN" -m "$M" -ngl 0 -t 3 -c 8192 --embeddings --pooling mean \
  --host 0.0.0.0 --port 8080
