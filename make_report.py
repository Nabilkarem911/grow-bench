"""make_report.py — يجمّع الأرقام المصحّحة في تقرير واحد + نص لتيليجرام."""
import json, os, glob

R = "F:/projects/grow/data/results/"

def load(n):
    p = R + n
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None

def bpc(d):
    return None if not d else round(d.get("loss_mean", 0) / 0.6931471805599453 * d.get("tokens_per_char", 0), 3)

rep = {"baseline_correct": load("evalhf_FIXED_base.json"),
       "trained_fixed": load("evalhf_FIXED_armB.json"),
       "trained_old_buggy": load("evalhf_FIXED_old_armB.json"),
       "trained_grown_fixed": load("evalhf_FIXED_armA.json"),
       "filter_base": load("task_base_before.json"),
       "filter_old": load("task_ours_arabic.json"),
       "cpu": load("cpu_bench.json")}

rows = {}
for k in ["baseline_correct", "trained_fixed", "trained_old_buggy", "trained_grown_fixed"]:
    d = rep[k]
    if d:
        n = max(1, d.get("windows", 1))
        rows[k] = {"bits_per_char": bpc(d), "loss": round(d.get("loss_mean", 0), 5),
                   "se": round((d.get("loss_std") or 0) / n ** 0.5, 5), "params": d.get("params")}

# الفرق المعنوي بين أي ذراعين (بوحدات الخطأ المعياري)
sig = {}
if "trained_grown_fixed" in rows and "trained_fixed" in rows:
    a, b = rows["trained_grown_fixed"], rows["trained_fixed"]
    diff = b["loss"] - a["loss"]
    se = (a["se"] ** 2 + b["se"] ** 2) ** 0.5
    sig = {"grown_vs_base_arm": {"diff_nats": round(diff, 5), "se": round(se, 5),
                                 "sigmas": round(diff / se, 2) if se else None}}
out = {"rows": rows, "significance": sig,
       "filter": {k: ({"auc": rep[k]["auc"], "acc": rep[k]["test_accuracy"]} if rep[k] else None)
                  for k in ["filter_base", "filter_old"]},
       "cpu": rep["cpu"]}
json.dump(out, open(R + "corrected_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("\n=== الأرقام المصحّحة (بت/حرف — أقل = أفهم) ===")
names = {"baseline_correct": "الأساس (بدون تدريب)",
         "trained_fixed": "بعد تدريب عربي (مُصلَّح)",
         "trained_old_buggy": "القديم المضرور (تدريب مخرّب)",
         "trained_grown_fixed": "المكبَّر + تدريب مُصلَّح"}
for k, v in rows.items():
    print(f"  {names.get(k, k):32s} {v['bits_per_char']}")
print(f"\nكتبت: {R}corrected_report.json")
