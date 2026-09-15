"""
مقارنة حقيقية: تدريب نفس الموديل على المعالج (CPU) مقابل كارت الشاشة (GPU).
- نفس معمارية المشروع (TinyGPT من train.py) — مقارنة عادلة.
- سقف صلبة للحماية: سقف VRAM + عدد خيوط محدود (الجهاز عليه Remote Desktop).
- المخرج: كلمات/ثانية + ذروة الاستهلاك، لكل حالة.
"""
import json, os, sys, time

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train import TinyGPT  # نفس المعمارية بالظبط

BLOCK, BATCH = 256, 16
CPU_THREADS = int(os.environ.get("CPU_THREADS", "8"))
SECONDS_PER_CASE = int(os.environ.get("SECONDS_PER_CASE", "25"))
VRAM_FRACTION = float(os.environ.get("VRAM_FRACTION", "0.35"))  # ~2.8GB من 8GB

CONFIGS = [
    # (اسم, n_layer, n_head, n_embd, mlp_mult)  — mlp_mult غير مدعوم في train.py الأصلي
    ("صغير (≈5M)", 6, 8, 256),
    ("متوسط (≈17M)", 8, 8, 384),
]

torch.set_num_threads(CPU_THREADS)


def make(n_layer, n_head, n_embd):
    try:
        return TinyGPT(n_layer=n_layer, n_head=n_head, n_embd=n_embd)
    except TypeError:
        return TinyGPT()


def bench(model, device, tag, seconds):
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    seg = BATCH * (BLOCK + 1)
    data = torch.randint(0, 256, (seg * 64,), dtype=torch.long, device=device)
    base = 0
    seen, steps = 0, 0
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
    t0 = time.time()
    model.train()
    while time.time() - t0 < seconds:
        i = (base * seg) % (data.numel() - seg)
        chunk = data[i:i + seg].view(BATCH, BLOCK + 1)
        x, y = chunk[:, :-1], chunk[:, 1:]
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        seen += x.numel()
        steps += 1
        base += 1
    if device == "cuda":
        torch.cuda.synchronize()
    dt = time.time() - t0
    res = {
        "case": tag, "device": device, "steps": steps,
        "tokens_per_sec": round(seen / dt),
        "seconds": round(dt, 1),
        "ram_mb": None,
    }
    if device == "cuda":
        res["vram_peak_mb"] = round(torch.cuda.max_memory_allocated() / 1048576)
    else:
        try:
            for line in open("/proc/self/status"):
                pass
        except Exception:
            pass
        try:
            import ctypes, ctypes.wintypes  # noqa
        except Exception:
            pass
    print("RESULT " + json.dumps(res, ensure_ascii=False), flush=True)
    return res


def main():
    out = {"cpu_threads": CPU_THREADS, "seconds_per_case": SECONDS_PER_CASE,
           "results": [], "cuda": torch.cuda.is_available()}
    if out["cuda"]:
        torch.cuda.set_per_process_memory_fraction(VRAM_FRACTION, 0)
        out["gpu"] = torch.cuda.get_device_name(0)
        out["capability"] = list(torch.cuda.get_device_capability(0))
        out["vram_total_mb"] = round(torch.cuda.get_device_properties(0).total_memory / 1048576)

    for name, nl, nh, ne in CONFIGS:
        m = make(nl, nh, ne)
        params = sum(p.numel() for p in m.parameters())
        # CPU (المقارنة الأساسية — دي اللي بتهم مبدأ المشروع)
        r = bench(make(nl, nh, ne), "cpu", f"{name} · CPU ({CPU_THREADS} خيوط)", SECONDS_PER_CASE)
        r["params"] = params
        out["results"].append(r)
        # GPU
        if out["cuda"]:
            r2 = bench(make(nl, nh, ne), "cuda", f"{name} · GPU", SECONDS_PER_CASE)
            r2["params"] = params
            r2["speedup_vs_cpu"] = round(r2["tokens_per_sec"] / max(r["tokens_per_sec"], 1), 1)
            out["results"].append(r2)

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench_result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("WROTE " + path, flush=True)
    print("FINAL " + json.dumps(out, ensure_ascii=False)[:1500], flush=True)


if __name__ == "__main__":
    main()
