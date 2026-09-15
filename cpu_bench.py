"""
cpu_bench.py — قياس حقيقي على المعالج: سرعة القراءة والجودة قبل/بعد الضغط لـ 8 بت.
الغرض: إثبات «موديل عربي شغال على أجهزة تعبانة» بأرقام.
الاستخدام: python cpu_bench.py --model <path> [--threads 8]
"""
import argparse, json, math, os, time

os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

CORPUS = "F:/projects/grow/data/corpus.txt"
PROMPTS = ["في صباح اليوم التالي", "اللغة العربية هي", "قال العالم"]
L2 = math.log(2)


def quality(model, ids, windows, block=256, batch=4):
    losses = []
    model.eval()
    with torch.no_grad():
        for s in range(0, windows, batch):
            xs, ys = [], []
            for w in range(s, min(s + batch, windows)):
                seg = ids[w * block:(w + 1) * block + 1]
                xs.append(seg[:-1]); ys.append(seg[1:])
            if not xs:
                break
            out = model(input_ids=torch.stack(xs), labels=torch.stack(ys))
            losses.append(float(out.loss.item()))
    return sum(losses) / len(losses)


def speed(model, tok, n=40):
    rates = []
    model.eval()
    with torch.no_grad():
        for p in PROMPTS:
            enc = tok(p, return_tensors="pt").input_ids
            t = time.time()
            o = model.generate(enc, max_new_tokens=n, do_sample=True, temperature=0.8,
                               top_p=0.95, pad_token_id=tok.eos_token_id, use_cache=True)
            dt = time.time() - t
            rates.append((o.shape[1] - enc.shape[1]) / dt)
    return sum(rates) / len(rates)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--quiet-check", type=int, default=200)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)

    res = {"stage": "cpu_bench", "model": a.model, "threads": a.threads, "cpu": os.environ.get("PROCESSOR_IDENTIFIER", "?")}
    tok = AutoTokenizer.from_pretrained(a.model)
    text = open(CORPUS, encoding="utf-8").read()
    val = text[int(0.98 * len(text)):]
    ids = tok(val, return_tensors="pt").input_ids[0]
    n_win = min(a.quiet_check, (ids.numel() - 1) // 256)

    m = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32)
    m.eval()
    mb = sum(p.numel() for p in m.parameters()) * 4 / 1048576
    t = time.time()
    loss32 = quality(m, ids, n_win)
    res["fp32"] = {"size_mb": round(mb, 1), "bits_per_char": round(loss32 / L2 * (ids.numel() / len(val)), 3),
                   "loss": round(loss32, 5), "quality_seconds": round(time.time() - t, 1)}
    t = time.time()
    res["fp32"]["tok_per_sec"] = round(speed(m, tok), 1)
    res["fp32"]["gen_seconds"] = round(time.time() - t, 1)
    print(f"fp32 | {mb:.0f} ميجا | {res['fp32']['tok_per_sec']} كلمة/ث | بت/حرف {res['fp32']['bits_per_char']}", flush=True)

    t = time.time()
    q = torch.ao.quantization.quantize_dynamic(m, {torch.nn.Linear}, dtype=torch.qint8)
    q.eval()
    res["quantize_seconds"] = round(time.time() - t, 1)
    t = time.time()
    loss8 = quality(q, ids, n_win)
    res["int8"] = {"bits_per_char": round(loss8 / L2 * (ids.numel() / len(val)), 3),
                   "loss": round(loss8, 5), "quality_seconds": round(time.time() - t, 1)}
    t = time.time()
    res["int8"]["tok_per_sec"] = round(speed(q, tok), 1)
    res["int8"]["gen_seconds"] = round(time.time() - t, 1)
    print(f"int8 | {res['int8']['tok_per_sec']} كلمة/ث | بت/حرف {res['int8']['bits_per_char']}", flush=True)

    res["speedup_x"] = round(res["int8"]["tok_per_sec"] / max(res["fp32"]["tok_per_sec"], 1e-9), 2)
    res["quality_delta_bits"] = round(res["int8"]["bits_per_char"] - res["fp32"]["bits_per_char"], 3)
    os.makedirs("F:/projects/grow/data/results", exist_ok=True)
    json.dump(res, open("F:/projects/grow/data/results/cpu_bench.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("CPU_RESULT " + json.dumps(res, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
