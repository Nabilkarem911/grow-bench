#!/bin/sh
LOG=/data/results/full_audit.log
mkdir -p /data/results
exec > "$LOG" 2>&1
echo "════════ فحص تيتان الشامل والناقد ════════"
python3 /app/full_audit.py
echo ""
python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok = os.environ.get("GITHUB_TOKEN", "")
if not tok: raise SystemExit
data = open("/data/results/full_audit.log", "rb").read().decode("utf-8", "ignore")
api = "https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/full_audit.log"
hdr = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "fawkes"}
sha = None
try:
    d = json.load(urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60)); sha = d.get("sha")
except Exception: pass
body = {"message": "full critical audit", "content": base64.b64encode(data.encode()).decode()}
if sha: body["sha"] = sha
print("✅", json.load(urllib.request.urlopen(urllib.request.Request(api, data=json.dumps(body).encode(), headers=hdr, method="PUT"), timeout=90)).get("content", {}).get("path"))
UPLOAD
