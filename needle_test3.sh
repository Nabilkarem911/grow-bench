#!/bin/sh
# needle_test3.sh — الحالة الحقيقية: رسائل عملاء مخلوطة (عربي + إنجليزي + أرقام)
LOG=/data/results/needle_test3.log
mkdir -p /data/results
exec > "$LOG" 2>&1
cd /data/needle || exit 1

cat > /tmp/extract.json <<'EOF'
[{"type":"function","function":{"name":"record_customer_issue","description":"Record a customer complaint/order issue from a WhatsApp message","parameters":{"type":"object","properties":{"customer_name":{"type":"string"},"phone":{"type":"string"},"order_id":{"type":"string"},"amount":{"type":"number"},"problem":{"type":"string"},"urgency":{"type":"string","enum":["low","medium","high"]}},"required":["customer_name","phone","problem"]}}}]
EOF

run() {
  echo ""; echo "=============================================="; echo "▶ $1"; echo "=============================================="
  shift
  timeout 240 ./needle "$@" 2>&1
}

echo "###### ١) رسالة مخلوطة: عربي + أرقام إنجليزي ######"
run "mixed-1" --model needle3.cact --tools /tmp/extract.json \
 --prompt 'السلام عليكم، أنا أحمد، phone 0555987654، order 7745، المبلغ 890 SAR، الطلب اتأخر 5 أيام ومحتاج حل'

echo ""
echo "###### ٢) رسالة بالإنجليزي جواها عربي للأكل ######"
run "mixed-2" --model needle3.cact --tools /tmp/extract.json \
 --prompt 'Hi, this is Sara. My number is 0566112233. Order #4412 for 320 SAR. The delivery is very late, I want my money back'

echo ""
echo "###### ٣) رسالة عربية خالص (سطر واحد واضح) ######"
run "ar-clean" --model needle3.cact --tools /tmp/extract.json \
 --prompt 'اسمي خالد رقمي 0500998877 عندي شكوى على الأوردر 1122'

echo ""
echo "###### ٤) وضع السيرفر مع reset بين كل طلب ######"
./needle --model needle3.cact --tools /tmp/extract.json --serve --port 8091 > /tmp/serve2.log 2>&1 &
SRV=$!
sleep 8
head -3 /tmp/serve2.log
python3 - <<'PYEOF'
import json, urllib.request, time
def call(inp, reset=True):
    if reset:
        try: urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/reset", data=b"{}", headers={"Content-Type":"application/json"}), timeout=30)
        except Exception: pass
    body=json.dumps({"input": inp}).encode()
    rq=urllib.request.Request("http://127.0.0.1:8091/complete", data=body, headers={"Content-Type":"application/json"})
    t0=time.time(); r=json.load(urllib.request.urlopen(rq, timeout=120))
    return r, round(time.time()-t0,2)
tests=[("مخلوط","السلام عليكم، أنا أحمد، phone 0555987654، order 7745، المبلغ 890 SAR، الطلب اتأخر 5 أيام ومحتاج حل"),
       ("إنجليزي","Hi, this is Sara. My number is 0566112233. Order #4412 for 320 SAR. The delivery is very late, I want my money back")]
for lbl,txt in tests:
    try:
        r,el=call(txt); print(f"[{lbl}] {el}ث →", json.dumps(r, ensure_ascii=False)[:450])
    except Exception as e: print(f"[{lbl}] فشل:", str(e)[:120])
PYEOF
kill $SRV 2>/dev/null
echo ""; echo "DONE-NEEDLE-TEST"

python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok=os.environ.get("GITHUB_TOKEN","")
if not tok: raise SystemExit
data=open("/data/results/needle_test3.log","rb").read().decode("utf-8","ignore")
api="https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/needle_test3.log"
hdr={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"needle"}
sha=None
try:
    d=json.load(urllib.request.urlopen(urllib.request.Request(api,headers=hdr),timeout=60)); sha=d.get("sha")
except Exception: pass
body={"message":"needle test round 3 (mixed AR/EN real customer messages + serve with reset)","content":base64.b64encode(data.encode()).decode()}
if sha: body["sha"]=sha
print("✅", json.load(urllib.request.urlopen(urllib.request.Request(api,data=json.dumps(body).encode(),headers=hdr,method="PUT"),timeout=90)).get("content",{}).get("path"))
UPLOAD
