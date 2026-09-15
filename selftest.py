"""
اختبار جهاز إلزامي — يمنع رجوع باج «الماسك على المعالج» (اللي كسر التدريب على الكارت).
بيتشغّل في الثانية: python selftest.py   (وبيرجّع كود خروج 0 لو كله تمام)
يفحص: بناء الموديل · خطوتين تدريب (CPU + كارت لو متاح) · النمو · التوليد — على الجهازين.
"""
import os, sys, traceback

import torch

from train import TinyGPT, generate, PROMPTS
import grow as grow_mod

FAILS = []


def check(name, fn):
    try:
        v = fn()
        print(f"  ✅ {name}" + (f" → {v}" if v is not None else ""), flush=True)
        return True
    except Exception as e:
        print(f"  ❌ {name} → {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        FAILS.append(name)
        return False


def one_run(device, n_layer=6, n_embd=256, steps=2, vocab=256, block=32, batch=4):
    """خطوتين تدريب حقيقيتين على الجهاز المطلوب — وتوليد نص. بيرجّع (loss, params)."""
    torch.manual_seed(0)
    model = TinyGPT(n_layer=n_layer, n_head=4, n_embd=n_embd).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    x = torch.randint(0, vocab, (batch, block), device=device)
    y = torch.randint(0, vocab, (batch, block), device=device)
    model.train()
    losses = []
    for _ in range(steps):
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        losses.append(round(loss.item(), 4))
    assert all(torch.isfinite(torch.tensor(losses))), f"loss مش سليم: {losses}"
    model.eval()
    sample = generate(model, PROMPTS[0], n=16, seed=7)
    assert isinstance(sample, str), "التوليد ما رجّعش نص"
    return losses, sum(p.numel() for p in model.parameters())


def grow_smoke(device):
    """النمو (عرض + عمق) على الجهاز المطلوب، والتأكد إن الدالة محفوظة (S1)."""
    torch.manual_seed(1)
    base = TinyGPT().to(device)
    base.eval()
    data = torch.randint(0, 256, (4096,), dtype=torch.long, device=device)
    x = data[100:100 + 32].unsqueeze(0)
    y = data[101:101 + 32].unsqueeze(0)
    with torch.no_grad():
        _, before = base(x, y)
    for b in base.blocks:
        grow_mod.widen_mlp(b)
    arch = dict(base.arch)
    arch["n_layer"] += 2
    arch["mlp_mult"] = grow_mod.MLP_MULT_NEW
    grown = TinyGPT(**arch).to(device)
    old = list(base.blocks)
    oi = 0
    with torch.no_grad():
        for i in range(arch["n_layer"]):
            if i in grow_mod.NEW_BLOCKS_AT:
                grown.blocks[i] = grow_mod.zero_block(arch["n_embd"], arch["n_head"],
                                                      grow_mod.MLP_MULT_NEW).to(device)
            else:
                grown.blocks[i] = old[oi]; oi += 1
        for name in ("tok", "pos", "lnf", "head"):
            getattr(grown, name).load_state_dict(getattr(base, name).state_dict())
    grown = grown.to(device)  # حماية إضافية: أي طبقة جديدة تتنقل لجهاز الموديل
    grown.eval()
    with torch.no_grad():
        _, after = grown(x, y)
    delta = abs(after.item() - before.item())
    return {"delta": round(delta, 8), "params": sum(p.numel() for p in grown.parameters()),
            "S1_pass": bool(delta < 1e-4)}


def main():
    print("=== selftest: دعم الأجهزة ===", flush=True)
    print(f"torch {torch.__version__} | cuda متاح: {torch.cuda.is_available()}", flush=True)
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)} | capability {torch.cuda.get_device_capability(0)}", flush=True)
    torch.set_num_threads(2)

    print("\n[1] CPU", flush=True)
    check("تدريب خطوتين + توليد على CPU", lambda: one_run(torch.device("cpu")))

    if torch.cuda.is_available():
        print("\n[2] GPU", flush=True)
        dev = torch.device("cuda")
        check("تدريب خطوتين + توليد على الكارت", lambda: one_run(dev))
        check("النمو (عرض+عمق) على الكارت", lambda: grow_smoke(dev))

    print("\n[3] النمو على CPU", flush=True)
    check("النمو (عرض+عمق) على CPU", lambda: grow_smoke(torch.device("cpu")))

    print("\n===== النتيجة =====", flush=True)
    if FAILS:
        print(f"❌ فشل: {FAILS}")
        sys.exit(1)
    print("✅ كل الفحوص نجحت")


if __name__ == "__main__":
    main()
