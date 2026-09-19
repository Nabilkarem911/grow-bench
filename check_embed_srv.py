#!/usr/bin/env python3
"""اختبار جودة خدمة التمثيل bge-m3 على العربي."""
import json, urllib.request, math, time

BASE = "http://embedsrv:8080/v1/embeddings"

def emb(text):
    rq = urllib.request.Request(BASE, data=json.dumps({"input": text}).encode("utf-8"),
                                headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(rq, timeout=300))["data"][0]["embedding"]

def cos(a, b):
    d = sum(x*y for x, y in zip(a, b))
    return d / (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b)))

print("=== الاتصال ===")
t0 = time.time(); v = emb("اختبار")
print(f"  ✅ الأبعاد: {len(v)} · الزمن: {round(time.time()-t0,2)} ث")

print("\n=== جودة العربي: هل التشابه بقى منطقي؟ ===")
pairs = [
    ("نفس المعنى  ", "الطلب اتأخر وأنا محتاج حل بسرعة", "أوردري متأخر ومحتاج مساعدة سريعة"),
    ("نفس المعنى ٢", "اسمي ابراهيم ورقمي 0555123456", "أنا ابراهيم تليفوني 0555123456"),
    ("نفس المعنى ٣", "عايز أعرف أسعار الشحن", "كام تكلفة التوصيل"),
    ("مختلف       ", "الطلب اتأخر وأنا محتاج حل بسرعة", "الطقس النهاردة جميل في ينبع"),
    ("مختلف ٢     ", "عايز أشتري لابتوب جديد", "فاتورة الكهرباء"),
    ("مختلف ٣     ", "إزاي أصلح كود بايثون", "أفضل مطعم في ينبع"),
    ("مختلف ٤     ", "شغل المحاسبة صعب", "ملعب الكورة بعيد"),
]
same, diff = [], []
for lbl, a, b in pairs:
    s = cos(emb(a), emb(b))
    print(f"  {lbl}  {s:.3f}")
    (same if lbl.startswith("نفس") else diff).append(s)

ms, md = sum(same)/len(same), sum(diff)/len(diff)
print(f"\n  متوسط «نفس المعنى»: {ms:.3f}")
print(f"  متوسط «مختلف»:      {md:.3f}")
print(f"  الفرق: {ms-md:.3f}  (المطلوب > 0.15)")
ok = ms > 0.85 and (ms - md) > 0.15
print("  ➜ " + ("✅ نجح — العربي بقى مفهوم ومميّز" if ok else "⚠️ لسه فيه مشكلة"))

if ok:
    print("\n=== بحث حقيقي: هل بيرجّع الحاجة الصح؟ ===")
    Q = "الطلب اتأخر ومحتاج حل بسرعة"
    items = ["الطقس النهاردة جميل في ينبع", "أوردري متأخر ومحتاج مساعدة سريعة",
             "فاتورة الكهرباء الشهرية", "عايز أشتري لابتوب جديد", "التوصيل اتأخر عن الميعاد"]
    qv = emb(Q)
    scored = sorted(((cos(qv, emb(it)), it) for it in items), reverse=True)
    for s, it in scored:
        print(f"   [{s:.3f}] {it}")
    print("   ➜ الأول صح؟", "✅ أيوة" if "متأخر" in scored[0][1] or "أوردري" in scored[0][1] else "❌ لأ")
