"""
task_wa_hybrid.py — الحل العملي: قواعد صارمة للحالات الواضحة + الموديل للباقي.
وكمان: كم استرجاع نقدر نحققه في فئة «الشكوى» (أهم فئة) عند دقة مقبولة؟

السؤال العملي: بدل ما نطلب من الموديل كل حاجة، نخليه يعمل اللي هو شاطر فيه بس.
"""
import json, os, re
os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
import numpy as np, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, precision_recall_curve

DATA = "F:/projects/grow/data/wa/labeled300.json"
OUT = "F:/projects/grow/data/results/task_wa_hybrid.json"
NAMES = {1: "شكوى/تأخير", 2: "طلب/تعديل", 3: "تعميد/موافقة", 4: "استفسار/تسعير", 5: "مجاملة/قصير"}
MODEL = "F:/projects/grow/data/ready/ft_armB_fixed"


def norm(t):
    t = re.sub(r"@[⁨~][^⁩\n]{0,30}⁩", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ===== قواعد صارمة (ثقة عالية) =====
GREET = re.compile(r"^(السلام عليكم( ورحمة الله( وبركاته)?)?|وعليكم السلام( ورحمة الله( وبركاته)?)?|"
                   r"صباح (الخير|النور)|مساء الخير|عيد .{0,20}مبارك|جمعة مباركة|باذن الله|ان شاء الله|"
                   r"آمين|امين|ابشر|حاضر( يا فندم)?|تمام|مشكور|تسلم|شكرا|شكراً|الله يعطيك العافية|"
                   r"علي راسي|ربنا ييسر.{0,20})[\s👍🏻🙏❤️🌹.!]*$")
APPROVE = re.compile(r"^(يعتمد|اعتمد|يعتمممم+د|نعم يعتمد|تم يعتمد|نعم نفذ|نعم صحيح)[\s👍🏻.!]*$")
NOISE = re.compile(r"^(\?+|\.+|؟+|👆🏻|@[⁨~][^⁩]*⁩|[\d.]+)$")

rows = json.load(open(DATA, encoding="utf-8"))
texts = [norm(r["text"]) for r in rows]
y = np.array([r["label"] for r in rows])


def rule_label(t):
    s = t.strip()
    if NOISE.match(s):
        return 5
    if APPROVE.match(s):
        return 3
    if GREET.match(s):
        return 5
    return None


rlab = np.array([rule_label(t) if rule_label(t) is not None else 0 for t in texts])
covered = rlab > 0
print(f"القواعد غطّت {covered.sum()}/{len(texts)} رسالة ({covered.mean()*100:.0f}%)")
if covered.sum():
    acc_rules = (rlab[covered] == y[covered]).mean()
    print(f"دقة القواعد على اللي غطّته: {acc_rules*100:.1f}%  (الحالات الواضحة)")

idx = np.arange(len(y))
tr, te = train_test_split(idx, test_size=100, random_state=42, stratify=y)

# ===== تمثيلات الموديل =====
dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32).to(dev).eval()
embs = []
with torch.no_grad():
    for i in range(0, len(texts), 16):
        enc = tok(texts[i:i + 16], return_tensors="pt", padding=True, truncation=True, max_length=256).to(dev)
        out = model(**enc, output_hidden_states=True)
        h = out.hidden_states[-1]
        m = enc["attention_mask"].unsqueeze(-1).float()
        embs.append(((h * m).sum(1) / m.sum(1).clamp(min=1)).float().cpu().numpy())
X = np.vstack(embs)
del model
torch.cuda.empty_cache()

clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0).fit(X[tr], y[tr])
pm = clf.predict(X[te])
acc_model = accuracy_score(y[te], pm)
print(f"\nالموديل لوحده على الاختبار: {acc_model*100:.1f}%")

# ===== الهجين: القواعد الأول، والموديل للباقي =====
ph = pm.copy()
for j, i in enumerate(te):
    r = rlab[i]
    if r > 0:
        ph[j] = r
acc_hybrid = accuracy_score(y[te], ph)
forced = sum(1 for i in te if rlab[i] > 0)
print(f"الهجين (قواعد + موديل):    {acc_hybrid*100:.1f}%   (القواعد حكمت على {forced} من {len(te)})")

# ===== فئة الشكوى: نجمع استرجاع عالي (الأهم عمليًا) =====
yb = (y == 1).astype(int)
clfb = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0).fit(X[tr], yb[tr])
pb = clfb.predict_proba(X[te])[:, 1]
prec, rec, thr = precision_recall_curve(yb[te], pb)
best_recall_at = {}
for target_p in [0.9, 0.8, 0.7, 0.6]:
    ok = prec >= target_p
    best_recall_at[target_p] = round(float(rec[ok].max()) if ok.any() else 0.0, 3)
f1b = f1_score(yb[te], (pb > 0.5).astype(int))
print(f"\n=== فئة الشكوى (فصل ثنائي: شكوى ضد الباقي) ===")
print(f"F1 عند العتبة 0.5: {f1b:.3f}")
for p, r in best_recall_at.items():
    print(f"  عند دقة {p*100:.0f}% → استرجاع {r*100:.0f}%")

res = {"rules_coverage": round(float(covered.mean()), 3),
       "rules_accuracy_on_covered": round(float((rlab[covered] == y[covered]).mean()), 4) if covered.sum() else None,
       "model_alone_acc": round(float(acc_model), 4),
       "hybrid_acc": round(float(acc_hybrid), 4),
       "complaint_binary_f1_05": round(float(f1b), 4),
       "complaint_recall_at_precision": best_recall_at,
       "n_test": len(te)}
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nاتحفظ:", OUT)
