"""
task_wa_classify.py — المهمة الحقيقية: تصنيف رسائل العملاء.

السؤال: هل الموديل بتاعنا أحسن من «حل بسيط بدون ذكاء اصطناعي»؟
الذراع: (أ) TF-IDF + انحدار لوجستي  ← الحل البسيط
       (ب) تمثيلات موديلنا العربي المدفّى + انحدار لوجستي
       (ج) تمثيلات الموديل الجاهز (قبل تدريب العربي) + انحدار لوجستي
تقسيم: 200 تدريب / 100 اختبار (طبقي، بذرة ثابتة)
"""
import json, os, re, time
os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
import numpy as np

DATA = "F:/projects/grow/data/wa/labeled300.json"
OUT = "F:/projects/grow/data/results/task_wa_classify.json"
NAMES = {1: "شكوى/تأخير", 2: "طلب/تعديل", 3: "تعميد/موافقة", 4: "استفسار/تسعير", 5: "مجاملة/قصير"}

MENTION = re.compile(r"@[⁨~][^⁩\n]{0,30}⁩")   # المنشنات (بدون أي أسماء)


def norm(t: str) -> str:
    """تنضيف بسيط: نشيل المنشنات والأسطر الفاضية."""
    t = re.sub(r"@[⁨~][^⁩\n]{0,30}⁩", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


rows = json.load(open(DATA, encoding="utf-8"))
texts = [norm(r["text"]) for r in rows]
y = np.array([r["label"] for r in rows])

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report

idx = np.arange(len(y))
tr, te = train_test_split(idx, test_size=100, random_state=42, stratify=y)
print(f"تدريب {len(tr)} · اختبار {len(te)}")

results = {}


def evaluate(name, X):
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=4.0)
    clf.fit(X[tr], y[tr])
    p = clf.predict(X[te])
    acc = accuracy_score(y[te], p)
    f1 = f1_score(y[te], p, average="macro")
    results[name] = {"accuracy": round(acc, 4), "macro_f1": round(f1, 4),
                     "report": classification_report(y[te], p, zero_division=0, output_dict=True)}
    print(f"\n■ {name}: دقة {acc*100:.1f}% · F1 (ماكرو) {f1:.3f}")
    return p


# (أ) الحل البسيط: TF-IDF
t0 = time.time()
vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, max_features=60000)
Xa = vec.fit_transform(texts)
pa = evaluate("A_tfidf_baseline", Xa)
results["A_tfidf_baseline"]["seconds"] = round(time.time() - t0, 1)

# (ب/ج) تمثيلات الموديلات
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

dev = "cuda" if torch.cuda.is_available() else "cpu"
for key, mid in [("B_ours_arabic", "F:/projects/grow/data/ready/ft_armB_fixed"),
                 ("C_ready_base", "Qwen/Qwen2.5-0.5B")]:
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(mid)
    model = AutoModelForCausalLM.from_pretrained(mid, dtype=torch.float32).to(dev).eval()
    embs = []
    with torch.no_grad():
        for i in range(0, len(texts), 16):
            b = texts[i:i + 16]
            enc = tok(b, return_tensors="pt", padding=True, truncation=True, max_length=256).to(dev)
            out = model(**enc, output_hidden_states=True)
            h = out.hidden_states[-1]                       # (B, T, D)
            m = enc["attention_mask"].unsqueeze(-1).float()  # (B, T, 1)
            embs.append(((h * m).sum(1) / m.sum(1).clamp(min=1)).float().cpu().numpy())
    Xe = np.vstack(embs)
    evaluate(key, Xe)
    results[key]["seconds"] = round(time.time() - t0, 1)
    results[key]["dim"] = int(Xe.shape[1])
    del model
    torch.cuda.empty_cache()

# ملخص
best = max(results, key=lambda k: results[k]["accuracy"])
print("\n" + "=" * 60)
for k in ["A_tfidf_baseline", "C_ready_base", "B_ours_arabic"]:
    if k in results:
        r = results[k]
        print(f"{k:<20} دقة {r['accuracy']*100:5.1f}%  F1 {r['macro_f1']:.3f}  ({r.get('seconds','?')}ث)")
print("=" * 60)
print(f"الأفضل: {best}")
json.dump({"results": results, "best": best, "n_train": len(tr), "n_test": len(te),
           "class_names": NAMES}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("اتحفظ:", OUT)
