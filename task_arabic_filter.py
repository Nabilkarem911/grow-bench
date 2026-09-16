"""
task_arabic_filter.py — أول قياس حقيقي: هل الموديل يفرّق بين نص عربي سليم ونص مخرّب؟

الفكرة: مهمة فلترة/تنقيح داتا عربية (الاستخدام العملي المقترح).
الوسوم مرجعية 100% (مبرمجة) → مفيش داتا إنتاجية ومفيش مخاطرة على أي شغل.

طريقة التقييم (بدون تدريب): الموديل بيدّي «تكلفة لكل حرف» — النص السليم تكلفته أقل.
نقيس: AUC + الدقة عند عتبة تختار من نصف الداتا وتُختبر على النص التاني (منع غش العتبة).

الاستخدام: python task_arabic_filter.py --model <path_or_id> --tag <name> [--n 200]
"""
import argparse, json, math, os, random, re, time, unicodedata

os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

CORPUS = "F:/projects/grow/data/corpus.txt"
L2 = math.log(2)
SEED = 20260916


def corrupt(s, rng):
    """تخريبات حقيقية بتحصل فعلًا في الداتا المسحوبة من الويب."""
    k = rng.randrange(8)
    if k == 0:                                  # مكسور ترميز (mojibake)
        return s.encode("utf-8").decode("latin-1", "replace")
    if k == 1:                                  # إنجليزي مخلوط جوّه العربي
        words = s.split()
        for _ in range(max(1, len(words) // 6)):
            words.insert(rng.randrange(len(words)), rng.choice(["init", "and", "the", "data", "OK"]))
        return " ".join(words)
    if k == 2:                                  # حذف/إضافة حروف (أخطاء)
        out = []
        for ch in s:
            r = rng.random()
            if r < 0.06:
                continue
            out.append(ch)
            if r > 0.97:
                out.append(rng.choice("ابتثجحخدذرزسشصضطظعغفقكلمنهوي"))
        return "".join(out)
    if k == 3:                                  # وسوم HTML وروابط وإيميلات
        return rng.choice(["<div>", "<p>", "<a href='x'>"]) + s + \
               rng.choice(["</div>", "</p>", " www.site.com", " info@mail.com", " http://x.y/z"])
    if k == 4:                                  # تكرار مفرط
        w = s.split()
        if len(w) > 4:
            i = rng.randrange(len(w) // 2)
            return " ".join(w[:i] + [w[i]] * 3 + w[i:])
        return s + s
    if k == 5:                                  # مسافات مقلوبة (كلمات ملزوقة)
        return re.sub(r"\s+", rng.choice(["", " "]), s[: max(10, len(s) // 2)])
    if k == 6:                                  # نص مقطوع
        return s[: max(8, len(s) // 4)]
    # رموز تشكيل مركّبة غريبة (بتظهر في نص مسحوب/مشوّه)
    marks = "\u064B\u064C\u064D\u0650\u0651\u0652\u0670"
    return "".join(c + (rng.choice(marks) if rng.random() < 0.25 else "") for c in s)


def bits_per_char(model, tok, text, dev):
    ids = tok(text, return_tensors="pt", add_special_tokens=False).input_ids
    if ids.shape[1] < 8:
        return None
    ids = ids.to(dev)
    with torch.no_grad():
        out = model(input_ids=ids, labels=ids)
    return float(out.loss.item()) / L2 * ids.shape[1] / max(len(text), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    rng = random.Random(SEED)
    dev = a.device

    raw = open(CORPUS, encoding="utf-8").read()
    # ناخد مقاطع نظيفة من آخر 2% (اللي مش مستخدمة في التدريب وقت التقييم الحتمي) عمليًا أي جزء نظيف
    pool = []
    step = max(300, len(raw) // (a.n * 40))
    i = rng.randrange(0, step)
    while len(pool) < a.n and i < len(raw) - 300:
        seg = raw[i:i + 220]
        seg = re.sub(r"\s+", " ", seg).strip()
        if len(seg) > 120 and re.search(r"[\u0600-\u06FF]", seg) and len(re.findall(r"[\u0600-\u06FF]", seg)) / len(seg) > 0.75:
            pool.append(seg)
        i += step + rng.randrange(0, 50)

    items = []
    for s in pool:
        items.append({"text": s, "label": 1})
        c = corrupt(s, rng)
        if len(c.strip()) < 20:
            c = s[: len(s) // 3] + " ... " + str(rng.randrange(10**6))
        items.append({"text": c, "label": 0})
    rng.shuffle(items)
    print(f"عيّنات: {len(items)} (نصيف: {sum(1 for x in items if x['label']==1)})", flush=True)

    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32).to(dev).eval()
    t0 = time.time()
    scores = []
    for n, it in enumerate(items):
        b = bits_per_char(model, tok, it["text"], dev)
        if b is None:
            b = 30.0
        scores.append(b)
        if n % 60 == 0:
            print(f"  ... {n}/{len(items)}", flush=True)
    # تكلفة أعلى = نص مخرّب → نرفع الإشارة بالعكس
    for it, sc in zip(items, scores):
        it["score"] = -sc

    # فصل العتبة عن الاختبار (نمنع غش العتبة)
    half = len(items) // 2
    cal, test = items[:half], items[half:]
    best_t, best_acc = None, -1
    cands = sorted({x["score"] for x in cal})
    for t in cands:
        acc = sum(1 for x in cal if (x["score"] >= t) == (x["label"] == 1)) / len(cal)
        if acc > best_acc:
            best_acc, best_t = acc, t

    def confusion(rows, t):
        tp = sum(1 for x in rows if x["score"] >= t and x["label"] == 1)
        fp = sum(1 for x in rows if x["score"] >= t and x["label"] == 0)
        fn = sum(1 for x in rows if x["score"] < t and x["label"] == 1)
        tn = sum(1 for x in rows if x["score"] < t and x["label"] == 0)
        return tp, fp, fn, tn

    tp, fp, fn, tn = confusion(test, best_t)
    acc = (tp + tn) / max(1, len(test))
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    fpr = fp / max(1, fp + tn)

    def auc(rows):
        pos = [x["score"] for x in rows if x["label"] == 1]
        neg = [x["score"] for x in rows if x["label"] == 0]
        if not pos or not neg:
            return None
        w = sum((1 if p > n else 0.5 if p == n else 0) for p in pos for n in neg)
        return w / (len(pos) * len(neg))

    bpc_clean = [ -x["score"] for x in items if x["label"] == 1]
    bpc_bad = [ -x["score"] for x in items if x["label"] == 0]
    res = {"stage": "task_arabic_filter", "tag": a.tag, "model": a.model, "device": dev,
           "n_items": len(items), "n_clean": len(bpc_clean), "n_corrupt": len(bpc_bad),
           "calibration_accuracy": round(best_acc, 4), "threshold": round(best_t, 4),
           "test_accuracy": round(acc, 4), "precision": round(prec, 4), "recall": round(rec, 4),
           "false_positive_rate_on_clean": round(fpr, 4), "auc": round(auc(test), 4),
           "mean_bits_per_char_clean": round(sum(bpc_clean) / len(bpc_clean), 3),
           "mean_bits_per_char_corrupt": round(sum(bpc_bad) / len(bpc_bad), 3),
           "seconds": round(time.time() - t0, 1)}
    os.makedirs("F:/projects/grow/data/results", exist_ok=True)
    json.dump(res, open(f"F:/projects/grow/data/results/task_{a.tag}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("TASK_RESULT " + json.dumps(res, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
