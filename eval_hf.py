"""
eval_hf.py — امتحان عربي حتمي لموديلات HuggingFace.
- يقيس loss على آخر 2% من الكوربوس العربي بكلام مارآهوش (نوافذ ثابتة بدون تراكب).
- نفس الطريقة المستخدمة في مشروعنا (sweep-256/256) عشان الأرقام مقارَنة.
- يطلّع samples من برومبتات عربية ثابتة + سرعة التوليد.
الاستخدام: python eval_hf.py --model <id_or_path> --tag <name> [--device cuda|cpu]
"""
import argparse, json, os, time

os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

CORPUS = "F:/projects/grow/data/corpus.txt"
PROMPTS = ["في صباح اليوم التالي", "اللغة العربية هي", "قال العالم", "المدينة الكبيرة"]
BLOCK = 256
BATCH = 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--max-windows", type=int, default=0)
    a = ap.parse_args()
    dev = a.device

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32).to(dev).eval()
    params = sum(p.numel() for p in model.parameters())

    text = open(CORPUS, encoding="utf-8").read()
    val = text[int(0.98 * len(text)):]
    ids = tok(val, return_tensors="pt").input_ids[0]
    n_win = (ids.numel() - 1) // BLOCK
    if a.max_windows:
        n_win = min(n_win, a.max_windows)

    losses = []
    with torch.no_grad():
        for s in range(0, n_win, BATCH):
            batch = []
            for w in range(s, min(s + BATCH, n_win)):
                batch.append(ids[w * BLOCK:(w + 1) * BLOCK + 1])
            if not batch:
                break
            x = torch.stack([b[:-1] for b in batch]).to(dev)
            y = torch.stack([b[1:] for b in batch]).to(dev)
            out = model(input_ids=x, labels=y)
            losses.append(float(out.loss.item()))

    samples = {}
    with torch.no_grad():
        for p in PROMPTS:
            enc = tok(p, return_tensors="pt").input_ids.to(dev)
            t = time.time()
            o = model.generate(enc, max_new_tokens=40, do_sample=True, temperature=0.8,
                               top_p=0.95, pad_token_id=tok.eos_token_id, use_cache=True)
            dt = time.time() - t
            samples[p] = {"text": tok.decode(o[0], skip_special_tokens=True),
                          "tok_per_sec": round((o.shape[1] - enc.shape[1]) / dt, 1)}

    res = {"stage": "eval_hf", "tag": a.tag, "model": a.model, "device": dev,
           "params": params, "size_mb": round(params * 4 / 1048576, 1),
           "val_chars": len(val), "val_tokens": int(ids.numel()),
           "tokens_per_char": round(ids.numel() / len(val), 3),
           "windows": n_win, "tokens_evaluated": int(n_win * BLOCK),
           "loss_mean": round(sum(losses) / len(losses), 5),
           "loss_std": round((sum((l - sum(losses) / len(losses)) ** 2 for l in losses) / len(losses)) ** 0.5, 5),
           "perplexity": round(2.718281828 ** (sum(losses) / len(losses)), 2),
           "batch_losses": [round(l, 4) for l in losses[:4]],
           "samples": samples, "eval_seconds": round(time.time() - t0, 1)}
    os.makedirs("F:/projects/grow/data/results", exist_ok=True)
    p = f"F:/projects/grow/data/results/evalhf_{a.tag}.json"
    json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("EVALHF " + json.dumps({k: v for k, v in res.items() if k != "samples"}, ensure_ascii=False), flush=True)
    print("SAMPLES " + json.dumps(samples, ensure_ascii=False)[:700], flush=True)
    print("WROTE " + p, flush=True)


if __name__ == "__main__":
    main()
