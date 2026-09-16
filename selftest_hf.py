"""
selftest_hf.py — حاجز يمنع باج «الزح المزدوج» في حساب الخسارة مع موديلات HuggingFace.

الفكرة: موديلات HF بتزح الإجابات لوحدها. فلو مرّرنا labels مزاحة يدويًا = زح مزدوج
= الموديل يتدرّب/يتقاس على «توقّع الكلمة اللي بعد الجاية» → أرقام مضللة (المفروض تكون أفضل بتبان أسوأ والعكس).

الاختبار بيقارن 3 طرق ويأكد إن الطريقة الصحيحة = الحساب اليدوي من الـlogits.

الاستخدام: python selftest_hf.py    (خروج 0 = سليم)
"""
import math, os, sys

os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = os.environ.get("SELFTEST_MODEL", "Qwen/Qwen2.5-0.5B")
TEXT = ("في صباح اليوم التالي خرج الناس إلى السوق ليشتروا ما يحتاجون، "
        "وكان الجو باردًا والسماء صافية. قال العالم إن اللغة العربية لغة الضاد.")
TOL = 1e-4


def main():
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32).to(dev).eval()
    ids = tok(TEXT, return_tensors="pt", add_special_tokens=False).input_ids.to(dev)
    results = {}
    with torch.no_grad():
        # (أ) الطريقة الصحيحة: labels = نفس المدخلات (المكتبة تزح لوحدها)
        results["correct_labels_eq_input"] = float(model(input_ids=ids, labels=ids).loss.item())
        # (ب) الزح اليدوي + زح المكتبة = زح مزدوج (الباج)
        results["double_shift_bug"] = float(
            model(input_ids=ids[:, :-1], labels=ids[:, 1:]).loss.item())
        # (ج) الحساب اليدوي المرجعي من الـlogits
        logits = model(input_ids=ids).logits[:, :-1].float()
        tgt = ids[:, 1:]
        ref = torch.nn.functional.cross_entropy(
            logits.reshape(-1, logits.size(-1)), tgt.reshape(-1)).item()
        results["manual_reference"] = ref

    print(f"الموديل: {MODEL} | عيّنة: {ids.shape[1]} كلمة")
    for k, v in results.items():
        print(f"  {k:26s} = {v:.6f}  ({v/math.log(2):.4f} بت)")
    ok_eq = abs(results["correct_labels_eq_input"] - results["manual_reference"]) < TOL
    ok_diff = abs(results["double_shift_bug"] - results["manual_reference"]) > 0.01
    print(f"\n  [1] الطريقة الصحيحة = المرجع اليدوي؟ {'✅' if ok_eq else '❌'} "
          f"(فرق {abs(results['correct_labels_eq_input']-results['manual_reference']):.2e})")
    print(f"  [2] الباج فعلاً مختلف عن الصح؟       {'✅' if ok_diff else '❌'} "
          f"(فرق {abs(results['double_shift_bug']-results['manual_reference']):.4f})")
    print(f"\n===== {'✅ الاختبار نجح — كود القياس سليم' if (ok_eq and ok_diff) else '❌ فشل — فيه زح مزدوج في الكود'} =====")
    raise SystemExit(0 if (ok_eq and ok_diff) else 1)


if __name__ == "__main__":
    main()
