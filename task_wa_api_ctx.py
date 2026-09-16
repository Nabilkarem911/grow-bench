"""
task_wa_api_ctx.py — تجربة السياق: نفس التصنيف لكن بآخر 3 رسائل قبل كل رسالة.
السؤال: هل السياق بيرفع الدقة؟ (لأن دي رسائل شات — السياق جزء من المعنى)
"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from sklearn.model_selection import train_test_split

ENV = {}
for l in open(os.path.expanduser("~/AppData/Local/hermes/.env"), encoding="utf-8", errors="ignore"):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.split("=", 1); ENV[k.strip()] = v.strip().strip('"').strip("'")

BASE = ENV["OPENAI_BASE_URL"].rstrip("/")
KEY = ENV["OPENAI_API_KEY"]
CTX = int(os.environ.get("CTX_N", "3"))

RUBRIC = """أنت مصنّف رسائل في شركة تغليف كرتون في السعودية.
هتوصلك محادثة واتساب، والمطلوب تصنيف **آخر رسالة** فيها فقط.
الفئات:
1 = شكوى أو تأخير أو استعجال أو مشكلة
2 = طلب جديد أو تعديل على طلب أو مواصفات
3 = تعميد أو موافقة (يعتمد/تم/اعتماد تصميم أو سعر)
4 = استفسار أو تسعير أو طلب/إرسال مستند
5 = مجاملة أو شكر أو رد قصير بلا طلب
لو فيها شكوى أو ضغط → 1. لو مجرد إشارة/رقم بلا معنى → 5.
اكتب الرقم فقط (1-5)."""

rows = json.load(open("F:/projects/grow/data/wa/labeled300.json", encoding="utf-8"))
y = np.array([r["label"] for r in rows])
tr, te = train_test_split(np.arange(len(y)), test_size=100, random_state=42, stratify=y)


def ask(args):
    import urllib.request
    model, txt = args
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 8,
                       "messages": [{"role": "system", "content": RUBRIC},
                                    {"role": "user", "content": txt}]}).encode()
    for a in range(3):
        try:
            req = urllib.request.Request(BASE + "/chat/completions", data=body,
                                         headers={"Authorization": "Bearer " + KEY,
                                                  "Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=90))
            m = re.search(r"[1-5]", d["choices"][0]["message"]["content"] or "")
            return int(m.group()) if m else None
        except Exception:
            time.sleep(2 + a * 2)
    return None


# ملاحظة: العينة مرتبة زمنيًا، فالرسائل السابقة للرسالة i هي i-CTX..i-1
calls = []
for i, r in enumerate(rows):
    prev = rows[max(0, i - CTX):i]
    if prev:
        ctx = "\n".join(f"[{p['sender'][:12] if p['sender'] else '?'}]: {p['text'][:180]}" for p in prev)
        txt = f"المحادثة (الأقدم للأحدث):\n{ctx}\n\nآخر رسالة (المطلوبة): {r['text'][:400]}"
    else:
        txt = f"آخر رسالة (المطلوبة): {r['text'][:400]}"
    calls.append((r["model"] if "model" in r else None, txt))

for model in (sys.argv[1:] or ["deepseek-v3.2-exp"]):
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(ask, [(model, c[1]) for c in calls]))
    preds = np.array([p if p else 0 for p in res])
    ok = preds > 0
    acc_all = (preds[ok] == y[ok]).mean()
    te_ok = [i for i in te if ok[i]]
    acc_te = (preds[te_ok] == y[te_ok]).mean()
    print(f"■ {model} (سياق {CTX} رسائل):  على 300 = {acc_all*100:.1f}%  |  على الـ100 = {acc_te*100:.1f}%  ({time.time()-t0:.0f}ث)")
    json.dump({"model": model, "ctx_n": CTX, "acc_all300": round(float(acc_all), 4),
               "acc_test100": round(float(acc_te), 4)},
              open(f"F:/projects/grow/data/results/task_wa_api_ctx{CTX}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
