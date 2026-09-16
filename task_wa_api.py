"""
task_wa_api.py — نفس مهمة التصنيف بموديل كبير عبر API (بإذن صريح من نبيل).
المقارنة: نفس الـ300 رسالة ونفس معيار التصنيف اللي استخدمته يدويًا.
بيرجّع: الدقة + التكلفة التقريبية (توكنز).
"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor

ENV = {}
for l in open(os.path.expanduser("~/AppData/Local/hermes/.env"), encoding="utf-8", errors="ignore"):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.split("=", 1); ENV[k.strip()] = v.strip().strip('"').strip("'")
BASE = ENV["OPENAI_BASE_URL"].rstrip("/")
KEY = ENV["OPENAI_API_KEY"]

RUBRIC = """أنت مصنّف رسائل في شركة تغليف كرتون في السعودية (G-Pack).
صنّف الرسالة لفئة واحدة فقط:
1 = شكوى أو تأخير أو استعجال أو مشكلة في منتج/شحنة/سعر
2 = طلب جديد أو تعديل على طلب أو مواصفات إنتاج
3 = تعميد أو موافقة (يعتمد/تم/اعتماد تصميم أو سعر)
4 = استفسار أو تسعير أو طلب/إرسال مستند (فاتورة، عرض سعر، بروفة، معلومة)
5 = مجاملة أو شكر أو رد قصير بلا طلب

انتبه: لو فيها شكوى أو ضغط أو استعجال → 1. لو مختصرة جدًا بلا معنى (؟؟ / 👆 / أرقام فقط) → 5.
اكتب الرقم فقط (1-5) بدون أي كلام آخر."""

rows = json.load(open("F:/projects/grow/data/wa/labeled300.json", encoding="utf-8"))


def ask(args):
    import urllib.request
    model, text = args
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 8,
                       "messages": [{"role": "system", "content": RUBRIC},
                                    {"role": "user", "content": text}]}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(BASE + "/chat/completions", data=body,
                                         headers={"Authorization": "Bearer " + KEY,
                                                  "Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=90))
            out = d["choices"][0]["message"]["content"]
            m = re.search(r"[1-5]", out or "")
            u = d.get("usage", {})
            return (int(m.group()) if m else None, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        except Exception:
            time.sleep(2 + attempt * 2)
    return (None, 0, 0)


MODELS = sys.argv[1:] or ["gpt-4o-mini", "deepseek-v3.2-exp"]
# نفس تقسيم التجربة المحلية (بذرة 42، 100 اختبار)
import numpy as np
from sklearn.model_selection import train_test_split
y = np.array([r["label"] for r in rows])
tr, te = train_test_split(np.arange(len(y)), test_size=100, random_state=42, stratify=y)

summary = {}
for model in MODELS:
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(ask, [(model, r["text"]) for r in rows]))
    preds = np.array([r[0] if r[0] else 0 for r in res])
    ok = preds > 0
    acc_all = (preds[ok] == y[ok]).mean()
    te_ok = [i for i in te if ok[i]]
    acc_te = (preds[te_ok] == y[te_ok]).mean()
    from sklearn.metrics import classification_report, f1_score
    rep = classification_report(y[te_ok], preds[te_ok], zero_division=0, output_dict=True)
    comp_f1 = rep.get("1", {}).get("f1-score")
    comp_rec = rep.get("1", {}).get("recall")
    pt = sum(r[1] for r in res); ct = sum(r[2] for r in res)
    summary[model] = {"acc_all300": round(float(acc_all), 4), "acc_test100": round(float(acc_te), 4),
                      "macro_f1_test100": round(float(f1_score(y[te_ok], preds[te_ok], average="macro")), 4),
                      "complaint_f1": round(float(comp_f1), 3) if comp_f1 else None,
                      "complaint_recall": round(float(comp_rec), 3) if comp_rec else None,
                      "n_answered": int(ok.sum()), "prompt_tokens": pt, "completion_tokens": ct,
                      "seconds": round(time.time() - t0, 1),
                      "per_class_test100": {k: round(float(v["f1-score"]), 3) for k, v in rep.items()
                                            if k in "12345"}}
    np.save(f"F:/projects/grow/data/results/api_preds_{model.replace('/', '_')}.npy", preds)
    print(f"■ {model}")
    print(f"   الدقة على 300: {acc_all*100:.1f}%  (روجعت {ok.sum()}/300)")
    print(f"   الدقة على نفس الـ100 اختبار: {acc_te*100:.1f}%")
    print(f"   توكنز: داخل {pt:,} · خارج {ct:,} · زمن {summary[model]['seconds']}ث")

json.dump({"summary": summary, "test_size": len(te)}, open("F:/projects/grow/data/results/task_wa_api.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nاتحفظ: data/results/task_wa_api.json (بدون أي نص رسائل)")
