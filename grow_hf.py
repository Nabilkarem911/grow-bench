"""
grow_hf.py — نمو محافظ على الدالة للموديلات الجاهزة (معمارية Llama/Qwen/SmolLM2).
نفس مبدأ grow.py بس على معماريات HuggingFace:
  (أ) توسيع طبقة الوسط في MLP (gate/up/down) بتقسيم مساهمة الوحدة المصدر نص-نص.
  (ب) تعميق: طبقات جديدة مخرجاتها مصفّرة (o_proj + down_proj = 0) → تضاف صفر بالظبط.

بوابة S1 إلزامية: loss على دفعة ثابتة قبل/بعد النمو لازم delta < 1e-4، وإلا النمو مكسور.

الاستخدام:
  python grow_hf.py --model <hf_id_or_path> --out <dir> [--mlp-add 384] [--depth-pos 8,16,24]
"""
import argparse, copy, json, os, time

os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def _set_linear(old, W, bias=None):
    """يصنع Linear بنفس جهاز/نوع الأوزان الأصلية."""
    import torch.nn as nn
    o, i = W.shape
    lin = nn.Linear(i, o, bias=bias is not None, device=W.device, dtype=W.dtype)
    with torch.no_grad():
        lin.weight.copy_(W)
        if bias is not None:
            lin.bias.copy_(bias)
    return lin


def widen_mlp(layer, n_new):
    """توسيع عرض MLP: تكرار n_new وحدة مصدر + تقسيم مساهمة مخرجاتها (Net2Net)."""
    mlp = layer.mlp
    if not hasattr(mlp, "gate_proj"):
        raise RuntimeError("grow_hf: الطبقة مش من نوع Llama/Qwen (مفيش gate_proj)")
    Wg = mlp.gate_proj.weight                       # (H, d)
    Wu = mlp.up_proj.weight
    Wd = mlp.down_proj.weight.clone()               # (d, H) — نسخة قبل التعديل
    H, d = Wg.shape
    n_new = min(n_new, H)
    src = torch.arange(n_new, device=Wg.device)

    g = torch.cat([Wg, Wg[src]], dim=0)
    u = torch.cat([Wu, Wu[src]], dim=0)
    dn = torch.cat([Wd, Wd[:, src] * 0.5], dim=1)
    dn[:, src] = Wd[:, src] * 0.5                   # النص التاني للمصدر

    mlp.gate_proj = _set_linear(mlp.gate_proj, g)
    mlp.up_proj = _set_linear(mlp.up_proj, u)
    mlp.down_proj = _set_linear(mlp.down_proj, dn)


def deepen(model, positions):
    """إدخال طبقات جديدة مخرجاتها صفر بالظبط → الدالة محفوظة 100%."""
    L = model.model.layers
    ref = L[0]
    dev = ref.self_attn.o_proj.weight.device
    dt = ref.self_attn.o_proj.weight.dtype
    added = []
    for pos in sorted(positions):
        pos = max(1, min(pos, len(L)))
        try:
            new = type(ref)(model.config, layer_idx=pos)   # transformers v5
        except TypeError:
            new = type(ref)(model.config)
        new = new.to(device=dev, dtype=dt)
        with torch.no_grad():
            new.self_attn.o_proj.weight.zero_()
            if new.self_attn.o_proj.bias is not None:
                new.self_attn.o_proj.bias.zero_()
            new.mlp.down_proj.weight.zero_()
            if new.mlp.down_proj.bias is not None:
                new.mlp.down_proj.bias.zero_()
        L.insert(pos, new)
        added.append(pos)
    # ⚠️ إلزامي: إعادة ترقيم كل الطبقات (والانتباه جواها كمان) عشان ميبقاش فيه ترقيم مكرر
    # (الترقيم المكرر بيعمل تعارض في كاش الانتباه/نوع الانتباه → المخرجات تتغيّر)
    for i, l in enumerate(L):
        for mod in l.modules():
            if hasattr(mod, "layer_idx"):
                mod.layer_idx = i
    model.config.num_hidden_layers = len(L)
    return added


def fixed_loss(model, ids, labels):
    model.eval()
    with torch.no_grad():
        return float(model(input_ids=ids, labels=labels).loss.item())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mlp-add", type=int, default=384, help="عدد وحدات تُضاف لعرض MLP")
    ap.add_argument("--depth-pos", default="", help="مواضع إدخال طبقات جديدة، مثال 8,16,24")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()

    dev = a.device
    res = {"stage": "grow_hf", "model": a.model, "device": dev, "mlp_add": a.mlp_add}
    tok = AutoTokenizer.from_pretrained(a.model)
    m = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32).to(dev).eval()
    p_before = sum(p.numel() for p in m.parameters())
    res["params_before"] = p_before
    res["layers_before"] = m.config.num_hidden_layers
    res["intermediate_before"] = getattr(m.config, "intermediate_size", None)

    # دفعة ثابتة لبوابة S1
    txt = "في البدء كان الكلمة، وكانت الكلمة عند الله. اللغة العربية لغة الضاد، " \
          "وفي صباح اليوم التالي خرج الناس إلى السوق ليشتروا ما يحتاجون."
    enc = tok(txt, return_tensors="pt")
    ids = enc.input_ids.to(dev)
    labels = ids.clone()

    with torch.no_grad():
        fix_before = fixed_loss(m, ids, labels)
    res["fixed_before"] = fix_before
    t0 = time.time()

    # (أ) توسيع MLP في كل الطبقات
    if a.mlp_add > 0:
        for layer in m.model.layers:
            if layer is not None:
                widen_mlp(layer, a.mlp_add)
        # إصلاح مقاسات المحفوظ
        m.config.intermediate_size = m.model.layers[0].mlp.gate_proj.weight.shape[0]

    # (ب) تعميق بطبقات مصفّرة
    pos = [int(x) for x in a.depth_pos.split(",") if x.strip()] if a.depth_pos else []
    res["depth_positions"] = deepen(m, pos) if pos else []

    with torch.no_grad():
        fix_after = fixed_loss(m, ids, labels)
    res["fixed_after"] = fix_after
    res["delta"] = abs(fix_after - fix_before)
    res["S1_pass"] = bool(res["delta"] < 1e-4)
    res["params_after"] = sum(p.numel() for p in m.parameters())
    res["layers_after"] = m.config.num_hidden_layers
    res["intermediate_after"] = m.config.intermediate_size
    res["grow_seconds"] = round(time.time() - t0, 1)

    if not res["S1_pass"]:
        res["stage"] = "failed_S1"
        print("FAIL " + json.dumps(res, ensure_ascii=False), flush=True)
        raise SystemExit(2)

    os.makedirs(a.out, exist_ok=True)
    m = m.to("cpu")
    m.save_pretrained(a.out, safe_serialization=True)
    tok.save_pretrained(a.out)
    res["saved_to"] = a.out
    res["stage"] = "done"
    os.makedirs("F:/projects/grow/data/results", exist_ok=True)
    json.dump(res, open("F:/projects/grow/data/results/grow_hf.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("GROW_RESULT " + json.dumps(res, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
