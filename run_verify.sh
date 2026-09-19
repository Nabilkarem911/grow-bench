#!/bin/sh
LOG=/data/results/arabic_memory_verify.log
mkdir -p /data/results
exec > "$LOG" 2>&1
echo "════════ تشخيص فشل بناء تيتان ════════"
echo "--- مساحة القرص ---"
df -h / /data 2>/dev/null | head -5
echo ""
echo "--- صورة التمثيل الحالية ---"
echo "(بنشوف هل النموذج الجديد ينفع يتنزّل ويتحمّل فعلًا)"
echo ""
echo "--- اختبار مباشر: fastembed 0.8.0 + e5-large ---"
pip install -q --disable-pip-version-check "fastembed==0.8.0" 2>&1 | tail -2
timeout 600 python3 - <<'PY'
import time
t0 = time.time()
try:
    from fastembed import TextEmbedding
    m = TextEmbedding("intfloat/multilingual-e5-large")
    v = list(m.embed(["اختبار"]))[0]
    print(f"  ✅ نجح! الأبعاد: {len(v)} · الزمن: {time.time()-t0:.0f} ثانية")
except Exception as e:
    print(f"  ❌ فشل بعد {time.time()-t0:.0f} ثانية: {type(e).__name__}: {str(e)[:300]}")
PY
echo ""
echo "--- مساحة القرص بعد ---"
df -h / | tail -2
echo ""
echo "DONE-ARABIC-VERIFY"
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
body={"message":"titan build failure diagnosis","content":base64.b64encode(data.encode()).decode()}
if sha: body["sha"]=sha
print("✅", json.load(urllib.request.urlopen(urllib.request.Request(api,data=json.dumps(body).encode(),headers=hdr,method="PUT"),timeout=90)).get("content",{}).get("path"))
UPLOAD
