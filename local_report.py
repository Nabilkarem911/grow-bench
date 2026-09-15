"""
تقرير الحكم النهائي لم3 (محلي) — يقرأ نتائج eval/grow/arm ويكتب الحكم بالأرقام.
شرط النجاح (§1): S1 (حفظ الدالة) · S2 (المكبَّر يغلّب من الصفر بنفس التوكنات) · S3 (مفيش نسيان).
"""
import glob, json, os

D = os.environ.get("DATA_DIR", "F:/projects/grow/data")
R = os.path.join(D, "results")


def load(name):
    p = os.path.join(R, name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def vl(ev):
    if not ev or not ev.get("val_mc4"):
        return None
    return ev["val_mc4"]["mean"]


def main():
    m1, ft, g0 = load("eval_m1_local.json"), load("eval_ft.json"), load("eval_grown0.json")
    g, a1, a2 = load("grow.json"), load("eval_arm1.json"), load("eval_arm2.json")
    arm1, arm2 = load("arm_arm1.json"), load("arm_arm2.json")

    out = {
        "stage": "report",
        "params": {
            "m1": (m1 or {}).get("params"),
            "grown": (g or {}).get("params_grown"),
            "arm1": (arm1 or {}).get("params"),
            "arm2": (arm2 or {}).get("params"),
        },
        "tokens": {
            "m1_local": (m1 or {}).get("ckpt_meta", {}).get("seen"),
            "arm1": (arm1 or {}).get("tokens_seen"),
            "arm2": (arm2 or {}).get("tokens_seen"),
        },
        "val_mc4": {
            "m1": vl(m1), "grown_untrained": vl(g0), "arm1": vl(a1), "arm2": vl(a2),
        },
        "val_factory": {
            "m1": (m1 or {}).get("val_factory", {}).get("mean"),
            "grown_untrained": (g0 or {}).get("val_factory", {}).get("mean"),
            "arm1": (a1 or {}).get("val_factory", {}).get("mean"),
            "arm2": (a2 or {}).get("val_factory", {}).get("mean"),
        },
        "samples_arm1": (a1 or {}).get("samples"),
        "samples_arm2": (a2 or {}).get("samples"),
        "S1": {
            "delta": (g or {}).get("delta"),
            "pass": bool((g or {}).get("S1_pass")),
            "note": "فرق loss على دفعة ثابتة قبل/بعد النمو — لازم < 1e-4",
        },
    }

    # S2: نفس التوكنات الإجمالية (arm1 = م1 + إضافي، arm2 = نفسه من الصفر)
    t1, t2 = out["tokens"]["arm1"], out["tokens"]["arm2"]
    v1, v2 = out["val_mc4"]["arm1"], out["val_mc4"]["arm2"]
    same_tokens = (t1 is not None and t2 is not None
                   and abs((t1 or 0) + (out["tokens"]["m1_local"] or 0) - (t2 or 0))
                   <= 2 * 256 * 16)
    out["S2"] = {
        "same_total_tokens": bool(same_tokens),
        "arm1_total_tokens": (t1 or 0) + (out["tokens"]["m1_local"] or 0),
        "arm2_total_tokens": t2,
        "arm1_val_mc4": v1, "arm2_val_mc4": v2,
        "delta": None if (v1 is None or v2 is None) else round(v2 - v1, 5),
        "pass": bool(v1 is not None and v2 is not None and v1 <= v2 - 0.02),
        "note": "arm1 لازم ≤ arm2 − 0.02 عند نفس إجمالي التوكنات",
    }

    # S3: النسيان — مقارنة arm1 بأساس م1 على mC4
    vm1, va1 = out["val_mc4"]["m1"], out["val_mc4"]["arm1"]
    out["S3"] = {
        "m1_val_mc4": vm1, "arm1_val_mc4": va1,
        "regression": None if (vm1 is None or va1 is None) else round(va1 - vm1, 5),
        "pass": bool(vm1 is not None and va1 is not None and (va1 - vm1) < 0.05),
        "note": "تراجع < 0.05 مقارنة بأساس م1 (الفاين-تيون سجّل +0.166 بلا نمو)",
    }

    # compute proxy
    def cp(tokens, params):
        return None if (tokens is None or params is None) else int(tokens * params)

    out["compute_proxy"] = {
        "arm1": cp(out["tokens"]["arm1"], out["params"]["arm1"]),
        # ⚠️ تصحيح: مرحلة الأساس اتدربت بباراميترات الأساس (4.94M) مش المكبَّرة
        "arm1_includes_base": (
            None if (out["tokens"]["m1_local"] is None or out["params"]["m1"] is None
                     or out["tokens"]["arm1"] is None or out["params"]["arm1"] is None)
            else int(out["tokens"]["m1_local"] * out["params"]["m1"]
                     + out["tokens"]["arm1"] * out["params"]["arm1"])
        ),
        "arm2": cp(out["tokens"]["arm2"], out["params"]["arm2"]),
    }
    a1b, a2b = out["compute_proxy"]["arm1_includes_base"], out["compute_proxy"]["arm2"]
    if a1b and a2b:
        out["compute_proxy"]["arm1_share_of_arm2"] = round(a1b / a2b, 4)
        # التجربة العادلة: arm2 بنفس حساب arm1 بالظبط
        out["compute_proxy"]["arm2_tokens_at_equal_compute"] = int(
            round(a1b / out["params"]["arm2"] / (256 * 16)) * 256 * 16)
    out["verdict"] = {
        "S1": out["S1"]["pass"], "S2": out["S2"]["pass"], "S3": out["S3"]["pass"],
        "passed_all": bool(out["S1"]["pass"] and out["S2"]["pass"] and out["S3"]["pass"]),
    }

    path = os.path.join(R, "final_local.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("FINAL " + json.dumps(out, ensure_ascii=False)[:1800], flush=True)
    print("WROTE " + path, flush=True)


if __name__ == "__main__":
    main()
