"""
نسخة مقارنة مستقلة (نفس معمارية train.py بالظبط) — بس فيها إصلاح جهاز الماسك
عشان الموديل يقدر يشتغل على الكارت. عدد الباراميترات لازم يطلع 4,935,680 للمقاس الصغير.
"""
import json, os, time

import torch, torch.nn as nn, torch.nn.functional as F

BLOCK, BATCH = 256, 16
CPU_THREADS = int(os.environ.get("CPU_THREADS", "8"))
SECONDS = int(os.environ.get("SECONDS_PER_CASE", "20"))
VRAM_FRACTION = float(os.environ.get("VRAM_FRACTION", "0.35"))


class Block(nn.Module):
    def __init__(self, n_embd, n_head):
        super().__init__()
        self.ln1 = nn.LayerNorm(n_embd)
        self.attn = nn.MultiheadAttention(n_embd, n_head, batch_first=True)
        self.ln2 = nn.LayerNorm(n_embd)
        self.mlp = nn.Sequential(nn.Linear(n_embd, 4 * n_embd), nn.GELU(),
                                 nn.Linear(4 * n_embd, n_embd))

    def forward(self, x):
        T = x.size(1)
        # ✅ الإصلاح: الماسك على نفس جهاز الدخل (كان على CPU دايماً)
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=x.device), diagonal=1)
        h = self.ln1(x)
        a, _ = self.attn(h, h, h, attn_mask=mask, need_weights=False)
        x = x + a
        return x + self.mlp(self.ln2(x))


class TinyGPT(nn.Module):
    def __init__(self, vocab=256, n_layer=6, n_head=8, n_embd=256, block=256):
        super().__init__()
        self.block = block
        self.tok = nn.Embedding(vocab, n_embd)
        self.pos = nn.Embedding(block, n_embd)
        self.blocks = nn.ModuleList([Block(n_embd, n_head) for _ in range(n_layer)])
        self.lnf = nn.LayerNorm(n_embd)
        self.head = nn.Linear(n_embd, vocab, bias=False)

    def forward(self, idx, targets=None):
        B, T = idx.shape
        x = self.tok(idx) + self.pos(torch.arange(T, device=idx.device))
        for b in self.blocks:
            x = b(x)
        logits = self.head(self.lnf(x))
        if targets is None:
            return logits, None
        return logits, F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))


def bench(cfg, device, seconds=SECONDS):
    nl, nh, ne = cfg
    torch.manual_seed(0)
    model = TinyGPT(n_layer=nl, n_head=nh, n_embd=ne).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    seg = BATCH * (BLOCK + 1)
    data = torch.randint(0, 256, (seg * 64,), dtype=torch.long, device=device)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize()
    model.train()
    seen = steps = 0; base = 0
    t0 = time.time()
    while time.time() - t0 < seconds:
        i = (base * seg) % (data.numel() - seg)
        chunk = data[i:i + seg].view(BATCH, BLOCK + 1)
        x, y = chunk[:, :-1], chunk[:, 1:]
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
        seen += x.numel(); steps += 1; base += 1
    if device == "cuda":
        torch.cuda.synchronize()
    dt = time.time() - t0
    r = {"cfg": cfg, "params": sum(p.numel() for p in model.parameters()), "device": device,
         "tokens_per_sec": round(seen / dt), "steps": steps, "seconds": round(dt, 1)}
    if device == "cuda":
        r["vram_peak_mb"] = round(torch.cuda.max_memory_allocated() / 1048576)
    print("RESULT " + json.dumps(r, ensure_ascii=False), flush=True)
    return r


def main():
    torch.set_num_threads(CPU_THREADS)
    out = {"cpu_threads": CPU_THREADS, "seconds_per_case": SECONDS,
           "cuda": torch.cuda.is_available(), "results": []}
    if out["cuda"]:
        torch.cuda.set_per_process_memory_fraction(VRAM_FRACTION, 0)
        out["gpu"] = torch.cuda.get_device_name(0)
        out["capability"] = list(torch.cuda.get_device_capability(0))
        out["vram_total_mb"] = round(torch.cuda.get_device_properties(0).total_memory / 1048576)
    for label, cfg in [("صغير", (6, 8, 256)), ("متوسط", (10, 8, 384))]:
        c = bench(cfg, "cpu"); c["label"] = label; out["results"].append(c)
        if out["cuda"]:
            g = bench(cfg, "cuda"); g["label"] = label
            g["speedup_vs_cpu"] = round(g["tokens_per_sec"] / max(c["tokens_per_sec"], 1), 1)
            out["results"].append(g)
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_bench.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("WROTE " + p, flush=True)


if __name__ == "__main__":
    main()
