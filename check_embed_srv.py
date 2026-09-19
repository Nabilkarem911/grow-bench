#!/usr/bin/env python3
"""اختبار خدمة التمثيل من حاوية الفحص — بنفس الشبكة، بالاسم مباشرة."""
import json, urllib.request, math, time

BASE = "http://embedsrv:8080/v1/embeddings"

def emb(text):
    rq = urllib.request.Request(BASE, data=json.dumps({"input": text, "model": "bge-m3"}).encode("utf-8"),
                                headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(rq, timeout=180))
    return r["data"][0]["embedding"]

def cos(a, b):
    d = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(y*y for y in b))
    return d / (na * nb)

print("=== الاتصال بالخدمة ===")
try:
    t0 = time.time()
    v = emb("اختبار")
    print(f"  ✅ شغالة · الأبعاد: {len(v)} · الزمن: {round(time.time()-t0,2)} ث")
except Exception as e:
    print("  ❌ فشل الاتصال:", str(e)[:250])
    raise SystemExit

print("\n=== اختبار العربي: هل التشابه بقى منطقي؟ ===")
pairs = [
    ("نفس المعنى  ", "الطلب اتأخر وأنا محتاج حل بسرعة", "أوردري متأخر ومحتاج مساعدة سريعة"),
    ("نفس المعنى ٢", "اسمي ابراهيم ورقمي 0555123456", "أنا ابراهيم تليفوني 0555123456"),
    ("مختلف       ", "الطلب اتأخر وأنا محتاج حل بسرعة", "الطقس النهاردة جميل في ينبع"),
    ("مختلف ٢     ", "عايز أشتري لابتوب جديد", "فاتورة الكهرباء الشهرية"),
    ("مختلف ٣     ", "إزاي أصلح كود بايثون", "أفضل مطعم في ينبع"),
]
same, diff = [], []
for lbl, a, b in pairs:
    s = cos(emb(a), emb(b))
    print(f"  {lbl}  {s:.3f}")
    (same if lbl.startswith("نفس") else diff).append(s)

ms, md = sum(same)/len(same), sum(diff)/len(diff)
print(f"\n  متوسط «نفس المعنى»: {ms:.3f}")
print(f"  متوسط «مختلف»:      {md:.3f}")
print(f"  الفرق: {ms-md:.3f}   (المطلوب > 0.15)")
print("  ➜ " + ("نجح ✓✓" if (ms > 0.85 and ms - md > 0.15) else "لسه محتاج تحسين ⚠️"))
