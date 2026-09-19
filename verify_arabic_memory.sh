#!/bin/sh
# verify_arabic_memory.sh — التحقق الفعلي من إصلاح الذاكرة العربية في تيتان
# الطريقة: ندخل جوّه حاوية التمثيل (عن طريق Docker socket) ونختبر العربي فعليًا
LOG=/data/results/arabic_memory_verify.log
mkdir -p /data/results
exec > "$LOG" 2>&1

echo "════════ ١) حاويات تيتان ════════"
docker ps --format '{{.Names}}\t{{.Status}}' | grep -i titan

EMBED=$(docker ps --format '{{.Names}}' | grep -i "titan.*embed" | head -1)
PG=$(docker ps --format '{{.Names}}' | grep -i "titan.*postgres" | head -1)
echo ""
echo "حاوية التمثيل: $EMBED"
echo "حاوية قاعدة البيانات: $PG"

echo ""
echo "════════ ٢) النموذج والأبعاد (من جوه الحاوية) ════════"
docker exec "$EMBED" python3 -c "
import json, urllib.request
try:
    d = json.load(urllib.request.urlopen('http://localhost:8000/health', timeout=30))
    print('  الموديل:', d.get('model'))
    print('  الأبعاد:', d.get('dimensions'))
except Exception as e:
    print('  فشل:', str(e)[:120])
"

echo ""
echo "════════ ٣) اختبار العربي الفعلي (المهم) ════════"
docker exec "$EMBED" python3 -c "
from fastembed import TextEmbedding
import numpy as np
m = TextEmbedding()
def vec(t): return list(m.embed([t]))[0]
def cos(x, y): return float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y)))

pairs = [
    ('نفس المعنى',        'الطلب اتأخر وأنا محتاج حل بسرعة',      'أوردري متأخر ومحتاج مساعدة سريعة'),
    ('نفس المعنى ٢',      'اسمي ابراهيم ورقمي 0555123456',        'أنا ابراهيم، تليفوني ٠٥٥٥١٢٣٤٥٦'),
    ('موضوع مختلف',       'الطلب اتأخر وأنا محتاج حل بسرعة',      'الطقس النهاردة جميل في ينبع'),
    ('موضوع مختلف ٢',     'عايز أشتري لابتوب جديد',               'الفاتورة الشهرية للكهرباء'),
]
print('  المقارنة                          التشابه')
print('  ' + '─'*52)
same, diff = [], []
for label, a, b in pairs:
    s = cos(vec(a), vec(b))
    print(f'  {label:32} {s:.3f}')
    (same if 'نفس' in label else diff).append(s)

print()
print(f'  ✦ متوسط «نفس المعنى»: {np.mean(same):.3f}  (المطلوب > 0.75)')
print(f'  ✦ متوسط «مختلف»:      {np.mean(diff):.3f}  (المطلوب أقل)')
verdict = 'نجح ✓' if np.mean(same) > 0.75 and np.mean(same) > np.mean(diff) + 0.15 else 'فشل ✗'
print(f'  ➜ الحكم: {verdict}')
"

echo ""
echo "════════ ٤) المخزون الفعلي (embedding_vec) ════════"
if [ -n "$PG" ]; then
  docker exec "$PG" psql -U postgres -d titan -t -c "
    SELECT 'إجمالي العناصر: ' || COUNT(*)::text FROM memory_items;
  " 2>&1 | head -3
  docker exec "$PG" psql -U postgres -d titan -t -c "
    SELECT 'فيهم متجه: ' || COUNT(*)::text FROM memory_items WHERE embedding_vec IS NOT NULL;
  " 2>&1 | head -3
  docker exec "$PG" psql -U postgres -d titan -t -c "
    SELECT 'نوع العمود: ' || format_type(a.atttypid, a.atttypmod)
    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
    WHERE c.relname='memory_items' AND a.attname='embedding_vec';
  " 2>&1 | head -3
fi

echo ""
echo "DONE-ARABIC-VERIFY"

python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok=os.environ.get("GITHUB_TOKEN","")
if not tok: raise SystemExit("no token")
data=open("/data/results/arabic_memory_verify.log","rb").read().decode("utf-8","ignore")
api="https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/arabic_memory_verify.log"
hdr={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"fawkes"}
sha=None
try:
    d=json.load(urllib.request.urlopen(urllib.request.Request(api,headers=hdr),timeout=60)); sha=d.get("sha")
except Exception: pass
body={"message":"Arabic memory verification log","content":base64.b64encode(data.encode()).decode()}
if sha: body["sha"]=sha
print("✅ اترفع:", json.load(urllib.request.urlopen(urllib.request.Request(api,data=json.dumps(body).encode(),headers=hdr,method="PUT"),timeout=90)).get("content",{}).get("path"))
UPLOAD
