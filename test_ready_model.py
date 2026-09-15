"""
اختبار موديل جاهز: هل يشتغل على الكارت وعلى المعالج؟ وبيولّد كم كلمة في الثانية؟
الاستخدام: python test_ready_model.py <model_id> [--cpu]
"""
import os, sys, time, json

os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

PROMPTS = ["اللغة العربية هي", "The capital of France is", "في صباح اليوم التالي كان"]


def run(mid, devices):
    out = {"model": mid, "results": {}}
    tok = AutoTokenizer.from_pretrained(mid)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    for dev in devices:
        t0 = time.time()
        m = AutoModelForCausalLM.from_pretrained(mid, dtype=torch.float32).to(dev).eval()
        load_s = time.time() - t0
        params = sum(p.numel() for p in m.parameters())
        per_dev = {"params": params, "load_seconds": round(load_s, 1),
                   "size_mb": round(params * 4 / 1048576, 1)}
        gen = {}
        with torch.no_grad():
            for p in PROMPTS:
                ids = tok(p, return_tensors="pt").input_ids.to(dev)
                if dev.startswith("cuda"):
                    torch.cuda.reset_peak_memory_stats()
                t = time.time()
                o = m.generate(ids, max_new_tokens=40, do_sample=True, temperature=0.8,
                               top_p=0.95, pad_token_id=tok.pad_token_id)
                dt = time.time() - t
                n = o.shape[1] - ids.shape[1]
                txt = tok.decode(o[0], skip_special_tokens=True)
                gen[p] = {"text": txt, "new_tokens": int(n),
                          "tok_per_sec": round(n / dt, 1), "seconds": round(dt, 2)}
        per_dev["generation"] = gen
        if dev.startswith("cuda"):
            per_dev["vram_peak_mb"] = round(torch.cuda.max_memory_allocated() / 1048576)
        out["results"][dev] = per_dev
        del m
        if dev.startswith("cuda"):
            torch.cuda.empty_cache()
    return out


if __name__ == "__main__":
    mid = sys.argv[1]
    devs = ["cuda", "cpu"] if torch.cuda.is_available() and "--cpu" not in sys.argv else ["cpu"]
    r = run(mid, devs)
    safe = mid.replace("/", "__")
    p = f"F:/projects/grow/data/results/ready_{safe}.json"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(json.dumps(r, ensure_ascii=False, indent=1))
    for dev, d in r["results"].items():
        g = d["generation"]
        best = next(iter(g.values()))
        print(f"READY {mid} | {dev} | params {d['params']:,} | {d['size_mb']}MB | "
              f"{best['tok_per_sec']} توكن/ث | تحميل {d['load_seconds']}ث"
              + (f" | VRAM {d.get('vram_peak_mb')}MB" if 'vram_peak_mb' in d else ""), flush=True)
    print("WROTE " + p, flush=True)
