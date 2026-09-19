#!/bin/sh
# needle_test.sh — تجربة Needle 3 على سيرفر نبيل (ARM64 · بلا كارت)
# الهدف: (١) هل يشتغل؟ (٢) هل يفهم العربي في استدعاء الأدوات؟
set -e
D=/data/needle
mkdir -p "$D"
cd "$D"

python3 - <<'PYEOF'
import os, urllib.request
B = "https://huggingface.co/Cactus-Compute/needle3/resolve/main/"
FILES = [("linux-arm64/needle", "needle"), ("needle3.cact", "needle3.cact")]
for src, dst in FILES:
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        print("موجود:", dst); continue
    print("بنزّل:", src, flush=True)
    urllib.request.urlretrieve(B + src, dst)
    print("  ✅", dst, round(os.path.getsize(dst)/1024), "كيلو", flush=True)
PYEOF
chmod +x needle

echo ""
echo "═══ ١) الواجهة (--help) ═══"
./needle --help 2>&1 | head -60 || echo "(--help فشل)"

echo ""
echo "═══ ٢) بدون معطيات ═══"
./needle 2>&1 | head -40 || true

echo ""
echo "═══ ٣) محاولة تشغيل ═══"
./needle needle3.cact "say hi" 2>&1 | head -30 || true

echo ""
echo "═══ ٤) أدوات + عربي ═══"
cat > /tmp/tools.json <<'EOF'
[{"type":"function","function":{"name":"send_whatsapp","description":"Send a WhatsApp message to a customer","parameters":{"type":"object","properties":{"phone":{"type":"string"},"text":{"type":"string"}},"required":["phone","text"]}}},
 {"type":"function","function":{"name":"check_order","description":"Check the status of a customer order","parameters":{"type":"object","properties":{"order_id":{"type":"string"}},"required":["order_id"]}}}]
EOF
echo "-- عربي --"
./needle needle3.cact --tools /tmp/tools.json "ابعت واتساب للعميل على 966501234567 وقوله إن الأوردر اتأخر" 2>&1 | head -40 || true
echo "-- إنجليزي (للمقارنة) --"
./needle needle3.cact --tools /tmp/tools.json "send a whatsapp to 966501234567 telling them the order is late" 2>&1 | head -40 || true
echo ""
echo "DONE-NEEDLE-TEST"
