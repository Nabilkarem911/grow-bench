#!/bin/sh
LOG=/data/results/core_logs.log
mkdir -p /data/results
exec > "$LOG" 2>&1
echo "════════ لوجات core ════════"
python3 /app/core_logs.py
echo ""
python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok = os.environ.get("GITHUB_TOKEN", "")
if not tok: raise SystemExit
data = open("/data/results/core_logs.log", "rb").read().decode("utf-8", "ignore")
api = "https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/core_logs.log"
hdr = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "fawkes"}
sha = None
try:
    d = json.load(urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60)); sha = d.get("sha")
except Exception: pass
body = {"message": "core logs", "content": base64.b64encode(data.encode()).decode()}
if sha: body["sha"] = sha
print("✅", json.load(urllib.request.urlopen(urllib.request.Request(api, data=json.dumps(body).encode(), headers=hdr, method="PUT"), timeout=90)).get("content", {}).get("path"))
UPLOAD
