#!/bin/sh
# تشخيص: إيه اللي موجود على السيرفر فعلًا؟
LOG=/data/results/arabic_memory_verify.log
mkdir -p /data/results
{
  echo "════════ تشخيص الملفات على السيرفر ════════"
  echo "المسار الحالي: $(pwd)"
  echo ""
  echo "--- task.txt ---"
  cat /app/task.txt 2>&1 | head -3
  echo ""
  echo "--- سكربتات في /app ---"
  ls -la /app/*.sh /app/*.py 2>&1 | head -20
  echo ""
  echo "--- هل الثعبان موجود؟ ---"
  which python3 || echo "python3 مش موجود!"
  python3 --version 2>&1
  echo ""
  echo "--- أول أسطر من run_verify.sh ---"
  head -5 /app/run_verify.sh 2>&1
  echo ""
  echo "════════ تجربة تشغيل مباشرة ════════"
  python3 /app/verify_arabic_memory.py 2>&1 | head -40
  echo ""
  echo "DONE-ARABIC-VERIFY"
} > "$LOG" 2>&1

python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok=os.environ.get("GITHUB_TOKEN","")
if not tok: raise SystemExit
data=open("/data/results/arabic_memory_verify.log","rb").read().decode("utf-8","ignore")
api="https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/arabic_memory_verify.log"
hdr={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"fawkes"}
sha=None
try:
    d=json.load(urllib.request.urlopen(urllib.request.Request(api,headers=hdr),timeout=60)); sha=d.get("sha")
except Exception: pass
body={"message":"arabic verify diag","content":base64.b64encode(data.encode()).decode()}
if sha: body["sha"]=sha
print("✅", json.load(urllib.request.urlopen(urllib.request.Request(api,data=json.dumps(body).encode(),headers=hdr,method="PUT"),timeout=90)).get("content",{}).get("path"))
UPLOAD
