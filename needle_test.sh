#!/bin/sh
# needle_test.sh — تجربة Needle 3 بالطريقة الصح (بعد ما عرفنا الواجهة):
#   ١) هل يستدعي الأدوات بالعربي؟  ٢) هل «قصّ الموديل» (--depth) ينفع؟
LOG=/data/results/needle_test.log
mkdir -p /data/results
exec > "$LOG" 2>&1

D=/data/needle
mkdir -p "$D"
cd "$D" || exit 1

python3 - <<'PYEOF'
import os, urllib.request
B = "https://huggingface.co/Cactus-Compute/needle3/resolve/main/"
for src, dst in [("linux-arm64/needle", "needle"), ("needle3.cact", "needle3.cact")]:
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        print("موجود مسبقًا:", dst, round(os.path.getsize(dst)/1024), "كيلو"); continue
    print("بنزّل:", src, flush=True)
    urllib.request.urlretrieve(B + src, dst)
    print("  ✅", dst, round(os.path.getsize(dst)/1024), "كيلو", flush=True)
PYEOF
chmod +x needle

cat > /tmp/tools.json <<'EOF'
[{"type":"function","function":{"name":"send_whatsapp","description":"Send a WhatsApp message to a customer","parameters":{"type":"object","properties":{"phone":{"type":"string"},"text":{"type":"string"}},"required":["phone","text"]}}},
 {"type":"function","function":{"name":"check_order","description":"Check the status of a customer order","parameters":{"type":"object","properties":{"order_id":{"type":"string"}},"required":["order_id"]}}}]
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
  echo "[الزمن: $(( (t1-t0)/1000000 )) مللي ثانية · رمز الخروج: $rc]"
}

echo "###### ١) عربي: ابعت واتساب وقوله الأوردر اتأخر ######"
run "عربي" --model needle3.cact --tools /tmp/tools.json --prompt "ابعت واتساب للعميل على 966501234567 وقوله إن الأوردر بتاعه اتأخر"

echo ""
echo "###### ٢) إنجليزي (نفس الطلب للمقارنة) ######"
run "إنجليزي" --model needle3.cact --tools /tmp/tools.json --prompt "send a whatsapp to 966501234567 telling them the order is late"

echo ""
echo "###### ٣) عربي مختلط: أداتين ######"
run "أداتين" --model needle3.cact --tools /tmp/tools.json --prompt "شوف الأوردر رقم 5521 وابعت للعميل 966501234567 إنه اتأخر"

echo ""
echo "###### ٤) طلب مالوش أداة (المفروض يرجع فاضي مش يخمّن) ######"
run "مفيش أداة" --model needle3.cact --tools /tmp/tools.json --prompt "إيه الطقس النهاردة في ينبع؟"

echo ""
echo "###### ٥) اختبار «قصّ الموديل» (--depth) ######"
for d in 3 6 12; do
  run "عمق $d طبقة (نفس الطلب العربي)" --model needle3.cact --tools /tmp/tools.json --depth $d --prompt "ابعت واتساب للعميل على 966501234567 وقوله إن الأوردر بتاعه اتأخر"
done

echo ""
echo "###### ٦) الملفات ######"
ls -la needle needle3.cact

echo ""
echo "DONE-NEEDLE-TEST"

python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok=os.environ.get("GITHUB_TOKEN","")
if not tok:
    print("مفيش توكن — النتيجة محفوظة محليًا بس"); raise SystemExit
data=open("/data/results/needle_test.log","rb").read().decode("utf-8","ignore")
api="https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/needle_test.log"
hdr={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"needle"}
sha=None
try:
    d=json.load(urllib.request.urlopen(urllib.request.Request(api,headers=hdr),timeout=60)); sha=d.get("sha")
except Exception: pass
body={"message":"needle test log v2 (correct CLI + Arabic tool calls + depth ladder)","content":base64.b64encode(data.encode()).decode()}
if sha: body["sha"]=sha
rq=urllib.request.Request(api,data=json.dumps(body).encode(),headers=hdr,method="PUT")
print("✅ اترفع:", json.load(urllib.request.urlopen(rq,timeout=90)).get("content",{}).get("path"))
UPLOAD
