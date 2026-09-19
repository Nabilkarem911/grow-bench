#!/bin/sh
# needle_test2.sh — الجولة التانية:
#   ١) الطلب اللي مالوش أداة (إنجليزي) ٢) الاستخراج المنظم (عربي/إنجليزي)
#   ٣) أقصى قصّ (--depth 2)  ٤) وضع السيرفر (--serve)
LOG=/data/results/needle_test2.log
mkdir -p /data/results
exec > "$LOG" 2>&1

cd /data/needle || exit 1
ls -la needle needle3.cact 2>/dev/null

cat > /tmp/tools.json <<'EOF'
[{"type":"function","function":{"name":"send_whatsapp","description":"Send a WhatsApp message to a customer","parameters":{"type":"object","properties":{"phone":{"type":"string"},"text":{"type":"string"}},"required":["phone","text"]}}},
 {"type":"function","function":{"name":"check_order","description":"Check the status of a customer order","parameters":{"type":"object","properties":{"order_id":{"type":"string"}},"required":["order_id"]}}}]
EOF

cat > /tmp/extract.json <<'EOF'
[{"type":"function","function":{"name":"record_customer_issue","description":"Record a customer complaint from a messy WhatsApp message","parameters":{"type":"object","properties":{"customer_name":{"type":"string"},"phone":{"type":"string"},"order_id":{"type":"string"},"amount":{"type":"number"},"problem":{"type":"string"},"urgency":{"type":"string","enum":["low","medium","high"]}},"required":["customer_name","phone","problem"]}}}]
EOF

run() {
  echo ""
  echo "=============================================="
  echo "▶ $1"
  echo "=============================================="
  shift
  t0=$(date +%s%N)
  timeout 240 ./needle "$@" 2>&1
  rc=$?
  t1=$(date +%s%N)
  echo "[الزمن: $(( (t1-t0)/1000000 )) مللي · exit: $rc]"
}

echo "###### ١) طلب مالوش أداة — إنجليزي ######"
run "no-tool EN" --model needle3.cact --tools /tmp/tools.json --prompt "what is the weather in Yanbu today?"

echo ""
echo "###### ٢) طلب مالوش أداة — عربي ######"
run "no-tool AR" --model needle3.cact --tools /tmp/tools.json --prompt "إيه الطقس النهاردة في ينبع؟"

echo ""
echo "###### ٣) استخراج من رسالة عميل ملخبطة — عربي ######"
AR_MSG='السلام عليكم انا اسمي ابراهيم من جده رقمي 0555123456 طلبت اوردر رقم 8821 بمبلغ 1450 ريال من اسبوع و لسه ما وصلش والفلوس اتخصمت'
run "extract AR" --model needle3.cact --tools /tmp/extract.json --prompt "$AR_MSG"

echo ""
echo "###### ٤) نفس الاستخراج — إنجليزي ######"
EN_MSG='Hi, my name is Ibrahim from Jeddah, phone 0555123456. I ordered order 8821 for 1450 SAR a week ago and it never arrived. The money was deducted.'
run "extract EN" --model needle3.cact --tools /tmp/extract.json --prompt "$EN_MSG"

echo ""
echo "###### ٥) أقصى قصّ — عمق 2 طبقة ######"
run "depth 2" --model needle3.cact --tools /tmp/tools.json --depth 2 --prompt "send a whatsapp to 966501234567 telling them the order is late"

echo ""
echo "###### ٦) وضع السيرفر (--serve على 8090) ######"
./needle --model needle3.cact --tools /tmp/tools.json --serve --port 8090 > /tmp/serve.log 2>&1 &
SRV=$!
sleep 8
echo "--- سجل الإقلاع ---"; head -8 /tmp/serve.log
python3 - <<'PYEOF'
import json, urllib.request, time
def call(inp):
    body=json.dumps({"input": inp}).encode()
    rq=urllib.request.Request("http://127.0.0.1:8090/complete", data=body, headers={"Content-Type":"application/json"})
    t0=time.time()
    r=json.load(urllib.request.urlopen(rq, timeout=120))
    return r, round(time.time()-t0, 2)
for label, txt in [("عربي","ابعت واتساب للعميل على 966501234567 وقوله إن الأوردر اتأخر"),
                   ("إنجليزي","send a whatsapp to 966501234567 telling them the order is late")]:
    try:
        r,el=call(txt); print(f"[{label}] {el}ث →", json.dumps(r, ensure_ascii=False)[:400])
    except Exception as e:
        print(f"[{label}] فشل:", str(e)[:150])
PYEOF
echo "--- إغلاق ---"
kill $SRV 2>/dev/null

echo ""
echo "DONE-NEEDLE-TEST"

python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok=os.environ.get("GITHUB_TOKEN","")
if not tok: print("مفيش توكن"); raise SystemExit
data=open("/data/results/needle_test2.log","rb").read().decode("utf-8","ignore")
api="https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/needle_test2.log"
hdr={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"needle"}
sha=None
try:
    d=json.load(urllib.request.urlopen(urllib.request.Request(api,headers=hdr),timeout=60)); sha=d.get("sha")
except Exception: pass
body={"message":"needle test round 2 (no-tool, structured extraction AR/EN, depth 2, serve mode)","content":base64.b64encode(data.encode()).decode()}
if sha: body["sha"]=sha
rq=urllib.request.Request(api,data=json.dumps(body).encode(),headers=hdr,method="PUT")
print("✅ اترفع:", json.load(urllib.request.urlopen(rq,timeout=90)).get("content",{}).get("path"))
UPLOAD
