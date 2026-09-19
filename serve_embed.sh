#!/bin/sh
# serve_embed.sh — خدمة تمثيل (embeddings) متعددة اللغات على llama.cpp
# الموديل: bge-m3 (1024 بُعد · 100+ لغة · عربي متقدم)
M=${EMBED_MODEL:-/data/moe/bge-m3-f16.gguf}
URL=${EMBED_MODEL_URL:-https://huggingface.co/CompendiumLabs/bge-m3-gguf/resolve/main/bge-m3-f16.gguf}

# ⚠️ ندور على llama-server (مش مسار ثابت — الملف موجود في مكان مختلف كل مرة)
BIN=$(find /data -name "llama-server" -type f 2>/dev/null | head -1)
if [ -z "$BIN" ]; then
  BIN=$(find / -name "llama-server" -type f -not -path "*/proc/*" 2>/dev/null | head -1)
fi
echo "llama-server: ${BIN:-مش موجود}"

if [ -z "$BIN" ]; then
  echo "❌ مفيش llama-server — بنزّله..."
  mkdir -p /data/llama && cd /data/llama
  python3 - <<'PY' || { echo "فشل التنزيل"; sleep infinity; }
import json, urllib.request
r = json.load(urllib.request.urlopen("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest", timeout=120))
for a in r.get("assets", []):
    n = a["name"]
    if "bin-ubuntu-arm64" in n and n.endswith(".tar.gz"):
        print("بنزّل:", n, flush=True)
        urllib.request.urlretrieve(a["browser_download_url"], "/tmp/l.tar.gz")
        import tarfile
        tarfile.open("/tmp/l.tar.gz").extractall("/data/llama")
        print("✅ فكّينا الملفات"); break
PY
  BIN=$(find /data/llama -name "llama-server" -type f | head -1)
  echo "بعد التنزيل: ${BIN:-لسه مش موجود}"
fi

if [ -z "$BIN" ]; then echo "❌ فشل توفير llama-server"; sleep infinity; fi

if [ ! -f "$M" ]; then
  echo "⬇️ بنزّل موديل التمثيل (1.1 جيجا)..."
  python3 - "$URL" "$M" <<'PY' || { echo 'فشل تنزيل الموديل'; sleep infinity; }
import os, sys, urllib.request
url, dst = sys.argv[1], sys.argv[2]
pos = os.path.getsize(dst) if os.path.exists(dst) else 0
req = urllib.request.Request(url, headers={"Range": f"bytes={pos}-"} if pos else {})
with urllib.request.urlopen(req, timeout=3600) as r, open(dst, "ab" if pos else "wb") as f:
    while True:
        ch = r.read(1 << 20)
        if not ch: break
        f.write(ch)
print("✅ اتنزّل:", round(os.path.getsize(dst)/2**20), "ميجا")
PY
fi

chmod +x "$BIN" 2>/dev/null
echo "🚀 تشغيل خدمة التمثيل على 8080 (bge-m3)"
exec "$BIN" -m "$M" -ngl 0 -t 3 -c 8192 --embeddings --pooling mean --host 0.0.0.0 --port 8080
