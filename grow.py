"""
م3 خطوة 4 — نمو بيحافظ على الدالة بالظبط (Net2Net).
(أ) عرض MLP: 1024→1280 — كل وحدة مصدر بتتقسم: النسخة الجديدة بتاخد نص مساهمة المصدر.
(ب) عمق: 6→8 — بلوكين جداد مخرجاتهم مصفّرة (out_proj + آخر Linear في MLP) → identity عند التهيئة.
S1 إلزامي: |loss_fixed_batch قبل − بعد| < 1e-4 — لو فشل، ممنوع نكمل.
مخرج: /data/m3/grown.pt + /data/results/grow.json — ممنوع يلمس ملفات م1.
"""
import json, os, time

import torch
from train import TinyGPT, Block
from eval import read_bytes, fixed_batch_loss, CORPUS

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CKPT_IN = os.environ.get("CKPT", "").strip() or "/data/checkpoint.pt"
OUT = os.environ.get("OUT", "").strip() or os.path.join(DATA_DIR, "m3", "grown.pt")
THREADS = int(os.environ.get("THREADS", "3"))
NEW_BLOCKS_AT = [4, 6]  # مواضع البلوكين الجداد في النموذج المكبّر (0..7)
MLP_MULT_NEW = 5        # 1024 → 1280 وحدة مخفية
ADD_UNITS = 256

torch.set_num_threads(THREADS)
RESULTS = os.path.join(DATA_DIR, "results")
EXPECTED_M1_FIXED = 0.981422  # مرجع F1 — لازم يطلع بالظبط قبل النمو


def load_m1():
    obj = torch.load(CKPT_IN, map_location="cpu")
    arch = obj.get("arch") if isinstance(obj, dict) else None
    model = TinyGPT(**arch) if arch else TinyGPT()
    model.load_state_dict(obj["model"] if "model" in obj else obj)
    model.eval()
    return model


def widen_mlp(block):
    """Net2Net split: كل وحدة مصدر j بتتنسخ لوحدة جديدة، والاتنين بياخدوا نص W2."""
    mlp = block.mlp
    W1, b1, W2 = mlp[0].weight, mlp[0].bias, mlp[2].weight
    H = W1.shape[0]
    n_new = H // 4  # 1024 → +256 = 1280
    sources = list(range(0, H, H // n_new))[:n_new]  # موزّعة على المؤشرات الأصلية
    with torch.no_grad():
        new_W1 = torch.cat([W1, W1[sources].clone()], 0)
        new_b1 = torch.cat([b1, b1[sources].clone()], 0)
        new_W2 = torch.cat([W2, W2[:, sources].clone()], 1)
        new_W2[:, sources] *= 0.5
        new_W2[:, H:] *= 0.5
    import torch.nn as nn
    in_dim = W1.shape[1]
    lin1 = nn.Linear(in_dim, H + n_new)
    lin2 = nn.Linear(H + n_new, in_dim)
    with torch.no_grad():
        lin1.weight.copy_(new_W1); lin1.bias.copy_(new_b1)
        lin2.weight.copy_(new_W2); lin2.bias.copy_(mlp[2].bias)
    mlp[0], mlp[2] = lin1, lin2


def zero_block(n_embd, n_head, mlp_mult):
    """بلوك جديد مخرجاته صفر → residual = identity."""
    b = Block(n_embd, n_head, mlp_mult)
    with torch.no_grad():
        b.attn.out_proj.weight.zero_()
        b.attn.out_proj.bias.zero_()
        b.mlp[2].weight.zero_()
        b.mlp[2].bias.zero_()
    return b


def grow(model):
    """يبني الموديل المكبّر من م1: 8 بلوكات × mlp_mult=5."""
    arch = dict(model.arch)
    arch["n_layer"] = arch["n_layer"] + 2
    arch["mlp_mult"] = MLP_MULT_NEW
    g = TinyGPT(**arch)
    # (أ) وسّع MLP البلوكات القديمة أولًا
    for b in model.blocks:
        widen_mlp(b)
    # (ب) الترتيب الجديد: البلوكات القديمة في مواضعها + بلوكين صفريين في 4 و 6
    old = list(model.blocks)
    old_idx = 0
    with torch.no_grad():
        for i in range(arch["n_layer"]):
            if i in NEW_BLOCKS_AT:
                g.blocks[i] = zero_block(arch["n_embd"], arch["n_head"], MLP_MULT_NEW)
            else:
                g.blocks[i] = old[old_idx]
                old_idx += 1
        g.tok.load_state_dict(model.tok.state_dict())
        g.pos.load_state_dict(model.pos.state_dict())
        g.lnf.load_state_dict(model.lnf.state_dict())
        g.head.load_state_dict(model.head.state_dict())
    g.eval()
    return g


def main():
    res = {"stage": "starting", "ckpt_in": CKPT_IN, "out": OUT,
           "new_blocks_at": NEW_BLOCKS_AT, "mlp_mult_new": MLP_MULT_NEW}
    t0 = time.time()
    try:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        os.makedirs(RESULTS, exist_ok=True)
        mc4 = torch.tensor(list(read_bytes(CORPUS)), dtype=torch.long)
        mc4_train = mc4[:int(0.98 * mc4.numel())]

        model = load_m1()
        res["params_m1"] = sum(p.numel() for p in model.parameters())
        loss_before = fixed_batch_loss(model, mc4_train)
        res["fixed_before"] = loss_before
        res["f1_acceptance"] = (loss_before == EXPECTED_M1_FIXED)
        if not res["f1_acceptance"]:
            res["stage"] = "failed"
            res["error"] = (f"F1 acceptance: fixed_batch={loss_before} "
                            f"!= {EXPECTED_M1_FIXED} — التهيئة غلط، توقّف")
            raise RuntimeError(res["error"])

        grown = grow(model)
        res["params_grown"] = sum(p.numel() for p in grown.parameters())
        loss_after = fixed_batch_loss(grown, mc4_train)
        res["fixed_after"] = loss_after
        res["delta"] = abs(loss_after - loss_before)
        res["S1_pass"] = bool(res["delta"] < 1e-4)

        tmp = OUT + ".tmp"
        torch.save({"model": grown.state_dict(), "arch": grown.arch,
                    "grown_from": "m1", "delta": res["delta"]}, tmp)
        os.replace(tmp, OUT)
        res["stage"] = "done" if res["S1_pass"] else "failed_s1"
    except Exception as e:
        import traceback
        res["stage"] = "failed"; res["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    res["seconds"] = round(time.time() - t0, 1)
    out = os.path.join(RESULTS, "grow.json")
    with open(out + ".tmp", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    os.replace(out + ".tmp", out)
    print("GROW", json.dumps(res, ensure_ascii=False)[:800], flush=True)


if __name__ == "__main__":
    main()
