"""
م3 — بناء الكوربوس المخلوط مرة واحدة (يُستخدم في الذراعين).
mixed.txt = قسم تدريب mC4 (أول 98%) + أول 85% من داتا المصنع ×3.
ملاحظة: المصنع ×3 يستخدم أول 85% بس — آخر 15% هي val_factory وممنوع تدخل تدريب (§2.4).
يكتب /data/m3/mixed.txt + /data/results/mix.json — مش بيلمس ملفات م1.
"""
import json, os

DATA_DIR = os.environ.get("DATA_DIR", "/data")
M3 = os.path.join(DATA_DIR, "m3")
OUT = os.path.join(M3, "mixed.txt")
RESULTS = os.path.join(DATA_DIR, "results")


def main():
    os.makedirs(M3, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    mc4 = open(os.path.join(DATA_DIR, "corpus.txt"), "rb").read()
    mc4_train = mc4[:int(0.98 * len(mc4))]
    fac = open(os.path.join(DATA_DIR, "factory", "corpus_factory.txt"), "rb").read()
    fac_train = fac[:int(0.85 * len(fac))]  # آخر 15% = val_factory — ممنوع (§2.4)

    with open(OUT + ".tmp", "wb") as f:
        f.write(mc4_train)
        for _ in range(3):
            f.write(fac_train)
    os.replace(OUT + ".tmp", OUT)

    total = len(mc4_train) + 3 * len(fac_train)
    res = {"stage": "done", "mixed_bytes": total,
           "mc4_train_bytes": len(mc4_train),
           "factory_train_bytes_x3": 3 * len(fac_train),
           "factory_share": round(3 * len(fac_train) / total, 4),
           "out": OUT}
    with open(os.path.join(RESULTS, "mix.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("MIX", json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
