"""
م3 خطوة 2 — فاين-تيون على داتا المصنع بس.
- يحمّل /data/checkpoint.pt (م1) كاملًا: model + opt — قراءة فقط، ممنوع الكتابة فوقه.
- يتدرّب على أول 85% من corpus_factory.txt (F2: آخر 15% تحقّق — ممنوع تُشاف).
- كل المخرجات في /data/ft/ + /data/results/finetune.json.
"""
import json, math, os, signal, time, urllib.parse, urllib.request

import torch
from train import TinyGPT, generate, PROMPTS
from eval import read_bytes, eval_set, fixed_batch_loss, CORPUS, BLOCK

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CKPT_IN = os.environ.get("CKPT", "/data/checkpoint.pt").strip()
FT_DIR = os.environ.get("OUT", os.path.join(DATA_DIR, "ft")).strip()
TRAIN_SECONDS = int(os.environ.get("TRAIN_SECONDS", "1500"))
THREADS = int(os.environ.get("THREADS", "3"))
REPORT_EVERY = int(os.environ.get("REPORT_EVERY", "300"))
CKPT_EVERY = int(os.environ.get("CKPT_EVERY", "300"))
REPORT_URL = os.environ.get("REPORT_URL", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

torch.set_num_threads(THREADS)
FT_CKPT = os.path.join(FT_DIR, "ckpt.pt")
FACTORY_CORPUS = os.path.join(DATA_DIR, "factory", "corpus_factory.txt")
RESULTS_DIR = os.path.join(DATA_DIR, "results")
BATCH = 16
STOP = False


def _sig(*_):
    global STOP
    STOP = True


signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


def report(payload, tg=False):
    body = json.dumps(payload, ensure_ascii=False)
    print("REPORT " + body, flush=True)
    if REPORT_URL:
        try:
            req = urllib.request.Request(REPORT_URL, data=body.encode("utf-8"),
                                         headers={"Title": "grow M3 ft"})
            urllib.request.urlopen(req, timeout=20)
        except Exception as e:
            print("report-warn:", e, flush=True)
    if tg and TG_TOKEN and TG_CHAT:
        try:
            txt = (f"🔧 grow M3 finetune\nstage: {payload.get('stage')}\n"
                   f"steps: {payload.get('steps')} · loss "
                   f"{payload.get('loss_first')} → {payload.get('loss_last')}\n"
                   f"val_factory قبل/بعد: "
                   f"{payload.get('eval_before', {}).get('val_factory', {}).get('mean')} → "
                   f"{payload.get('eval_after', {}).get('val_factory', {}).get('mean')}\n"
                   f"{payload.get('error','')}"[:900])
            data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": txt}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                   data=data, timeout=20)
        except Exception as e:
            print("telegram-warn:", e, flush=True)


def save_ft(model, opt, steps, seen, elapsed):
    tmp = FT_CKPT + ".tmp"
    torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                "arch": model.arch, "base": "m1-finetune",
                "steps": steps, "seen": seen, "elapsed": elapsed,
                "rng": torch.get_rng_state()}, tmp)
    os.replace(tmp, FT_CKPT)


def write_state(st):
    p = os.path.join(FT_DIR, "state.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, p)


def get_batch(src):
    ix = torch.randint(len(src) - BLOCK - 1, (BATCH,))
    x = torch.stack([src[i:i + BLOCK] for i in ix])
    y = torch.stack([src[i + 1:i + BLOCK + 1] for i in ix])
    return x, y


def main():
    res = {"stage": "starting", "ckpt_in": CKPT_IN, "out": FT_DIR,
           "train_seconds": TRAIN_SECONDS, "threads": THREADS}
    t_start = time.time()
    try:
        os.makedirs(FT_DIR, exist_ok=True)
        os.makedirs(RESULTS_DIR, exist_ok=True)

        # تحميل m1 كاملًا (model+opt) — أو استكمال ft لو فيه checkpoint سابقة
        src = FT_CKPT if os.path.exists(FT_CKPT) else CKPT_IN
        obj = torch.load(src, map_location="cpu")
        arch = obj.get("arch") if isinstance(obj, dict) else None
        model = TinyGPT(**arch) if arch else TinyGPT()
        model.load_state_dict(obj["model"] if "model" in obj else obj)
        opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
        resumed = os.path.exists(FT_CKPT) and src == FT_CKPT
        steps, seen, prev_elapsed = 0, 0, 0.0
        if "opt" in obj:
            opt.load_state_dict(obj["opt"])
        if resumed:
            steps, seen, prev_elapsed = obj.get("steps", 0), obj.get("seen", 0), obj.get("elapsed", 0.0)
            torch.set_rng_state(obj["rng"])
        res["params"] = sum(p.numel() for p in model.parameters())
        res["resumed_ft"] = resumed
        res["arch"] = model.arch

        # داتا: mC4 للتقييم + أول 85% من المصنع للتدريب (F2)
        mc4 = torch.tensor(list(read_bytes(CORPUS)), dtype=torch.long)
        mc4_val = mc4[int(0.98 * mc4.numel()):]
        ft = torch.tensor(list(read_bytes(FACTORY_CORPUS)), dtype=torch.long)
        nf = int(0.85 * ft.numel())
        train, ft_val = ft[:nf], ft[nf:]
        res["factory_train_bytes"] = int(train.numel())
        res["factory_val_bytes"] = int(ft_val.numel())

        # التقييم الحتمي «قبل» (مسح كامل — F2)
        model.eval()
        res["eval_before"] = {
            "val_mc4": eval_set(model, mc4_val),
            "val_factory": eval_set(model, ft_val),
            "loss_fixed_batch": fixed_batch_loss(model, mc4[:int(0.98 * mc4.numel())]),
        }
        report({**res, "stage": "eval-before-done"}, tg=False)

        # التدريب على داتا المصنع فقط
        model.train()
        t0 = time.time()
        first_loss = last_loss = None
        last_ckpt = last_rep = time.time()
        rep_seen = seen

        while not STOP and (time.time() - t0 + prev_elapsed) < TRAIN_SECONDS:
            x, y = get_batch(train)
            _, loss = model(x, y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            if first_loss is None:
                first_loss = loss.item()
            last_loss = loss.item()
            steps += 1
            seen += x.numel()

            now = time.time()
            if now - last_ckpt >= CKPT_EVERY:
                save_ft(model, opt, steps, seen, now - t0 + prev_elapsed)
                last_ckpt = now
            if now - last_rep >= REPORT_EVERY:
                dt = now - last_rep
                st = {"stage": "running", "steps": steps, "tokens_seen": seen,
                      "tokens_per_sec": round((seen - rep_seen) / max(dt, 1)),
                      "loss_last": round(last_loss, 4),
                      "elapsed_s": round(now - t0 + prev_elapsed)}
                write_state(st)
                report({**st, "params": res["params"]}, tg=False)
                rep_seen, last_rep = seen, now

        elapsed = time.time() - t0 + prev_elapsed
        save_ft(model, opt, steps, seen, elapsed)

        # التقييم الحتمي «بعد» + عينات
        model.eval()
        res["eval_after"] = {
            "val_mc4": eval_set(model, mc4_val),
            "val_factory": eval_set(model, ft_val),
            "loss_fixed_batch": fixed_batch_loss(model, mc4[:int(0.98 * mc4.numel())]),
        }
        res["samples"] = {p: generate(model, p, 100, seed=1234) for p in PROMPTS}
        res.update({
            "stage": "stopped" if STOP else "done",
            "steps": steps, "tokens_seen": seen,
            "tokens_per_sec": round(seen / max(elapsed, 1)),
            "elapsed_seconds": round(elapsed, 1),
            "loss_first": round(first_loss, 4) if first_loss else None,
            "loss_last": round(last_loss, 4) if last_loss else None,
            "epochs_factory": round(seen / train.numel(), 2),
            "ft_ckpt_mb": round(os.path.getsize(FT_CKPT) / 1048576, 1),
        })
    except Exception as e:
        import traceback
        res["stage"] = "failed"; res["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    out = os.path.join(RESULTS_DIR, "finetune.json")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out)
    res["total_seconds"] = round(time.time() - t_start, 1)
    report(res, tg=True)


if __name__ == "__main__":
    main()
