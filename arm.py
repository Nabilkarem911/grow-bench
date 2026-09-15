"""
م3 خطوات 5/7 — مدرّب الذراع الواحد. F3+F5 مطبّقين هنا:
- INIT=مسار checkpoint للمعمارية (و/أو الأوزان). INIT_MODE=weights (arm1) | fresh (arm2).
- مُحسِّن جديد تمامًا AdamW lr=3e-4 في كل ذراع (F3.1) — ممنوع تحميل opt قديم.
- STOP_AT_TOKENS: توقف عند نفس عدد التوكنات بالظبط في الذراعين (F3.2).
- حاجز التلوث (F5.1): ممنوع INIT أو DATA أو OUT جوّه /data/ft.
- البيانات: mixed.txt الموحّد — ممنوع مزيج مختلف (§6.5).
- استكمال من OUT/ckpt.pt لو موجودة (opt بتاع الذراع نفسه — مش بتاع م1).
- يكتب OUT/ckpt.pt + /data/results/arm_<TAG>.json — ممنوع يلمس ملفات م1 أو ft.
"""
import json, math, os, signal, time, urllib.parse, urllib.request

import torch
from train import TinyGPT, generate, PROMPTS
from eval import read_bytes

DATA_DIR = os.environ.get("DATA_DIR", "/data")
INIT = os.environ.get("INIT", "").strip()
INIT_MODE = os.environ.get("INIT_MODE", "weights").strip()  # weights | fresh
OUT = os.environ.get("OUT", "").strip()
DATA = os.environ.get("DATA", "").strip() or os.path.join(DATA_DIR, "m3", "mixed.txt")
TAG = os.environ.get("TAG", "arm").strip() or "arm"
STOP_AT_TOKENS = int(os.environ.get("STOP_AT_TOKENS", "0"))
TRAIN_SECONDS = int(os.environ.get("TRAIN_SECONDS", "86400"))
THREADS = int(os.environ.get("THREADS", "3"))
REPORT_EVERY = int(os.environ.get("REPORT_EVERY", "900"))
CKPT_EVERY = int(os.environ.get("CKPT_EVERY", "600"))
REPORT_URL = os.environ.get("REPORT_URL", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

torch.set_num_threads(THREADS)
RESULTS = os.path.join(DATA_DIR, "results")
BLOCK, BATCH = 256, 16
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
                                         headers={"Title": "grow M3 arm"})
            urllib.request.urlopen(req, timeout=20)
        except Exception as e:
            print("report-warn:", e, flush=True)
    if tg and TG_TOKEN and TG_CHAT:
        try:
            txt = (f"💪 grow M3 {TAG}\nstage: {payload.get('stage')}\n"
                   f"steps: {payload.get('steps')} · tokens: {payload.get('tokens_seen')}\n"
                   f"loss {payload.get('loss_first')} → {payload.get('loss_last')} · "
                   f"{payload.get('tokens_per_sec')} tok/s\n{payload.get('error','')}"[:900])
            data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": txt}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                   data=data, timeout=20)
        except Exception as e:
            print("telegram-warn:", e, flush=True)


def usage():
    u = {"threads": THREADS}
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS"):
                u["rss_mb"] = int(line.split()[1]) // 1024
    except Exception:
        pass
    try:
        u["load1"] = round(os.getloadavg()[0], 2)
    except Exception:
        pass
    return u


def barrier(path, what):
    """F5.1 — ممنوع أي مسار جوّه /data/ft."""
    ft = os.path.join(DATA_DIR, "ft")
    if os.path.abspath(path).startswith(os.path.abspath(ft) + os.sep):
        raise RuntimeError(f"contamination barrier: {what} داخل /data/ft ممنوع: {path}")


def save_ckpt(path, model, opt, steps, seen, elapsed):
    tmp = path + ".tmp"
    torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                "arch": model.arch, "arm": TAG,
                "steps": steps, "seen": seen, "elapsed": elapsed,
                "rng": torch.get_rng_state()}, tmp)
    os.replace(tmp, path)


def get_batch(src):
    ix = torch.randint(len(src) - BLOCK - 1, (BATCH,))
    x = torch.stack([src[i:i + BLOCK] for i in ix])
    y = torch.stack([src[i + 1:i + BLOCK + 1] for i in ix])
    return x, y


def main():
    res = {"stage": "starting", "tag": TAG, "init": INIT, "init_mode": INIT_MODE,
           "out": OUT, "data": DATA, "stop_at_tokens": STOP_AT_TOKENS,
           "threads": THREADS}
    t_start = time.time()
    try:
        if not OUT:
            raise RuntimeError("OUT لازم يتحدد")
        barrier(OUT, "OUT"); barrier(DATA, "DATA")
        if INIT:
            barrier(INIT, "INIT")
        os.makedirs(OUT, exist_ok=True)
        os.makedirs(RESULTS, exist_ok=True)
        ckpt_path = os.path.join(OUT, "ckpt.pt")

        data = torch.tensor(list(read_bytes(DATA)), dtype=torch.long)
        res["data_tokens"] = int(data.numel())

        steps, seen, prev_elapsed = 0, 0, 0.0
        if os.path.exists(ckpt_path):
            # استكمال الذراع نفسه بعد توقف — opt بتاعه هو (مسموح)
            ck = torch.load(ckpt_path, map_location="cpu")
            model = TinyGPT(**ck["arch"])
            model.load_state_dict(ck["model"])
            opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
            opt.load_state_dict(ck["opt"])
            steps, seen, prev_elapsed = ck["steps"], ck["seen"], ck["elapsed"]
            torch.set_rng_state(ck["rng"])
            res["resumed"] = True
        else:
            obj = torch.load(INIT, map_location="cpu")
            arch = obj.get("arch") if isinstance(obj, dict) else None
            if INIT_MODE == "weights":
                model = TinyGPT(**arch) if arch else TinyGPT()
                model.load_state_dict(obj["model"] if "model" in obj else obj)
            else:
                torch.manual_seed(1234)  # arm2: نفس المعمارية، أوزان جديدة ثابتة
                model = TinyGPT(**arch) if arch else TinyGPT()
            opt = torch.optim.AdamW(model.parameters(), lr=3e-4)  # F3.1: جديد دايمًا
            res["resumed"] = False

        res["params"] = sum(p.numel() for p in model.parameters())
        report({**res, "stage": "started"}, tg=False)

        stop = (STOP_AT_TOKENS // BLOCK) * BLOCK if STOP_AT_TOKENS else None
        res["stop_at_tokens_effective"] = stop

        model.train()
        t0 = time.time()
        first_loss = last_loss = None
        last_ckpt = last_rep = time.time()
        rep_seen = seen

        while not STOP and (time.time() - t0 + prev_elapsed) < TRAIN_SECONDS:
            if stop and seen >= stop:
                break
            rows = BATCH
            if stop and seen + BATCH * BLOCK > stop:
                rows = (stop - seen) // BLOCK  # آخر دفعة جزئية → توقف بالظبط
                if rows <= 0:
                    break
            ix = torch.randint(len(data) - BLOCK - 1, (rows,))
            x = torch.stack([data[i:i + BLOCK] for i in ix])
            y = torch.stack([data[i + 1:i + BLOCK + 1] for i in ix])
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
                save_ckpt(ckpt_path, model, opt, steps, seen, now - t0 + prev_elapsed)
                last_ckpt = now
            if now - last_rep >= REPORT_EVERY:
                dt = now - last_rep
                elapsed = now - t0 + prev_elapsed
                payload = {"stage": "running", "tag": TAG, "steps": steps,
                           "tokens_seen": seen, "stop_at": stop,
                           "tokens_per_sec": round((seen - rep_seen) / max(dt, 1)),
                           "elapsed_hours": round(elapsed / 3600, 2),
                           "loss_last": round(last_loss, 4),
                           "epochs_mixed": round(seen / data.numel(), 3),
                           "usage": usage()}
                with open(os.path.join(OUT, "state.json"), "w") as f:
                    json.dump(payload, f)
                report(payload, tg=False)
                rep_seen, last_rep = seen, now

        elapsed = time.time() - t0 + prev_elapsed
        save_ckpt(ckpt_path, model, opt, steps, seen, elapsed)
        res.update({
            "stage": "stopped" if STOP else "done",
            "steps": steps, "tokens_seen": seen,
            "tokens_per_sec": round(seen / max(elapsed, 1)),
            "elapsed_seconds": round(elapsed, 1),
            "elapsed_hours": round(elapsed / 3600, 2),
            "loss_first": round(first_loss, 4) if first_loss else None,
            "loss_last": round(last_loss, 4) if last_loss else None,
            "epochs_mixed": round(seen / data.numel(), 3),
            "compute_proxy_tokens_x_params": seen * res["params"],
            "usage": usage(),
            "samples": {p: generate(model, p, 100, seed=1234) for p in PROMPTS},
        })
    except Exception as e:
        import traceback
        res["stage"] = "failed"; res["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    res["total_seconds"] = round(time.time() - t_start, 1)
    out = os.path.join(RESULTS, f"arm_{TAG}.json")
    with open(out + ".tmp", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    os.replace(out + ".tmp", out)
    report(res, tg=True)


if __name__ == "__main__":
    main()
