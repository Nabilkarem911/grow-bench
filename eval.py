"""
م3 — مقياس حتمي واحد لكل التجارب.
يدخل: CKPT (checkpoint كامل أو state_dict) + TAG.
يطلّع: val_mc4 (mean±std على 64 دفعة ثابتة) + val_factory + loss_fixed_batch + عينات ثابتة.
يكتب: /data/results/eval_<TAG>.json — القناة الرسمية للنتائج.
"""
import json, math, os, time, urllib.parse, urllib.request

import torch
from train import TinyGPT, generate, PROMPTS

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CKPT = os.environ.get("CKPT", "/data/checkpoint.pt").strip()
TAG = os.environ.get("TAG", "m1").strip()
THREADS = int(os.environ.get("THREADS", "3"))
REPORT_URL = os.environ.get("REPORT_URL", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

RESULTS_DIR = os.path.join(DATA_DIR, "results")
CORPUS = os.path.join(DATA_DIR, "corpus.txt")
FACTORY_CORPUS = os.path.join(DATA_DIR, "factory", "corpus_factory.txt")
BLOCK, BATCH, NBATCH = 256, 16, 64

torch.set_num_threads(THREADS)


def report(payload, tg=True):
    body = json.dumps(payload, ensure_ascii=False)
    print("REPORT " + body, flush=True)
    if REPORT_URL:
        try:
            req = urllib.request.Request(REPORT_URL, data=body.encode("utf-8"),
                                         headers={"Title": "grow M3 eval"})
            urllib.request.urlopen(req, timeout=20)
        except Exception as e:
            print("report-warn:", e, flush=True)
    if tg and TG_TOKEN and TG_CHAT:
        try:
            txt = (f"📏 grow M3 eval — {TAG}\n"
                   f"val_mc4: {payload.get('val_mc4',{}).get('mean')} "
                   f"· val_factory: {payload.get('val_factory',{}).get('mean')}\n"
                   f"fixed_batch: {payload.get('loss_fixed_batch')}\n"
                   f"{payload.get('error','')}"[:900])
            data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": txt}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                   data=data, timeout=20)
        except Exception as e:
            print("telegram-warn:", e, flush=True)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def batches(data, nbatch, seed):
    """نفس الدفعات بالظبط كل مرة: مولّد واحد ببذرة ثابتة."""
    g = torch.Generator().manual_seed(seed)
    ix = torch.randint(len(data) - BLOCK - 1, (nbatch * BATCH,), generator=g)
    for i in range(nbatch):
        sel = ix[i * BATCH:(i + 1) * BATCH]
        x = torch.stack([data[j:j + BLOCK] for j in sel])
        y = torch.stack([data[j + 1:j + BLOCK + 1] for j in sel])
        yield x, y


@torch.no_grad()
def eval_set(model, data, nbatch=NBATCH, seed=1234):
    losses = []
    for x, y in batches(data, nbatch, seed):
        _, loss = model(x, y)
        losses.append(loss.item())
    mean = sum(losses) / len(losses)
    var = sum((l - mean) ** 2 for l in losses) / len(losses)
    return {"mean": round(mean, 5), "std": round(math.sqrt(var), 5), "batches": len(losses)}


@torch.no_grad()
def fixed_batch_loss(model, data):
    """دفعة واحدة ثابتة (بذرة 777 على قسم التدريب) — لمقارنة النمو S1."""
    x, y = next(batches(data, 1, 777))
    _, loss = model(x, y)
    return round(loss.item(), 6)


def load_model(path):
    obj = torch.load(path, map_location="cpu")
    meta = {}
    if isinstance(obj, dict) and "model" in obj:
        meta = {k: obj[k] for k in ("steps", "seen", "elapsed") if k in obj}
        obj = obj["model"]
    model = TinyGPT()
    model.load_state_dict(obj)
    model.eval()
    return model, meta


def main():
    res = {"tag": TAG, "ckpt": CKPT, "threads": THREADS, "stage": "starting"}
    t0 = time.time()
    try:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        model, meta = load_model(CKPT)
        res["params"] = sum(p.numel() for p in model.parameters())
        res["ckpt_meta"] = meta

        mc4 = torch.tensor(list(read_bytes(CORPUS)), dtype=torch.long)
        n = int(0.98 * mc4.numel())
        mc4_train, mc4_val = mc4[:n], mc4[n:]
        res["val_mc4"] = eval_set(model, mc4_val)
        res["loss_fixed_batch"] = fixed_batch_loss(model, mc4_train)

        if os.path.exists(FACTORY_CORPUS) and os.path.getsize(FACTORY_CORPUS) > 100_000:
            ft = torch.tensor(list(read_bytes(FACTORY_CORPUS)), dtype=torch.long)
            nf = int(0.9 * ft.numel())
            res["val_factory"] = eval_set(model, ft[nf:])
        else:
            res["val_factory"] = None

        res["samples"] = {p: generate(model, p, 100, seed=1234) for p in PROMPTS}
        res["eval_seconds"] = round(time.time() - t0, 1)
        res["stage"] = "done"
    except Exception as e:
        import traceback
        res["stage"] = "failed"; res["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    out_path = os.path.join(RESULTS_DIR, f"eval_{TAG}.json")
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_path)
    print("wrote", out_path, flush=True)
    report(res)


if __name__ == "__main__":
    main()
