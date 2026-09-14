"""
م1 — تدريب فعلي: موديل عربي ~5M باراميتر على CPU لساعات طويلة.
- كوربوس: mC4 العربي عبر HuggingFace datasets-server، مع كاش في DATA_DIR.
- checkpoints دورية + استكمال تلقائي بعد أي توقف + حفظ عند SIGTERM.
- تقارير ntfy كل REPORT_EVERY ثانية + تقرير نهائي بعينات توليد ثابتة.
"""
import json, math, os, signal, time, urllib.parse, urllib.request

import torch, torch.nn as nn, torch.nn.functional as F

DATA_DIR = os.environ.get("DATA_DIR", "/data")
TRAIN_SECONDS = int(os.environ.get("TRAIN_SECONDS", "28800"))
THREADS = int(os.environ.get("THREADS", "3"))
TARGET_CHARS = int(os.environ.get("TARGET_CHARS", "40000000"))
REPORT_EVERY = int(os.environ.get("REPORT_EVERY", "900"))
CKPT_EVERY = int(os.environ.get("CKPT_EVERY", "600"))
REPORT_URL = os.environ.get("REPORT_URL", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

torch.set_num_threads(THREADS)
CKPT_PATH = os.path.join(DATA_DIR, "checkpoint.pt")
CORPUS_PATH = os.path.join(DATA_DIR, "corpus.txt")
FINAL_PATH = os.path.join(DATA_DIR, "model_final.pt")
METRICS_PATH = os.path.join(DATA_DIR, "metrics.json")
PROMPTS = ["في البدء كان", "اللغة العربية", "وفي صباح اليوم التالي",
           "قال العالم", "المدينة الكبيرة"]
STOP = False


def _sig(*_):
    global STOP
    STOP = True


signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


def report(payload: dict, tg: bool = True):
    """يطلّع التقرير بره الكونتينر: ntfy + تيليجرام (للأحداث المهمة بس)."""
    body = json.dumps(payload, ensure_ascii=False)
    print("REPORT " + body, flush=True)
    if REPORT_URL:
        try:
            req = urllib.request.Request(REPORT_URL, data=body.encode("utf-8"),
                                         headers={"Title": "grow M1"})
            urllib.request.urlopen(req, timeout=20)
        except Exception as e:
            print("report-warn:", e, flush=True)
    if tg and TG_TOKEN and TG_CHAT:
        try:
            f = lambda k, d="—": (f"{payload.get(k):,}" if isinstance(payload.get(k), (int, float)) else d)
            txt = ("🌱 grow M1 — تدريب عربي على CPU\n"
                   f"stage: {payload.get('stage')}\n"
                   f"params: {f('params')} · tokens: {f('tokens_seen')} ({f('tokens_per_sec')}/s)\n"
                   f"loss: {f('loss_first')} → {f('loss_last')} · val {f('val_loss')}\n"
                   f"elapsed: {f('elapsed_hours')}h / {f('train_hours')}h\n"
                   f"{payload.get('error','')}"[:900])
            data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": txt}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                   data=data, timeout=20)
        except Exception as e:
            print("telegram-warn:", e, flush=True)


def usage():
    """استهلاك الموارد: RAM و load داخل الكونتينر."""
    u = {"threads": THREADS}
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS"):
                u["rss_mb"] = int(line.split()[1]) // 1024
    except Exception:
        pass
    try:
        u["mem_mb"] = int(open("/sys/fs/cgroup/memory.current").read()) // 1048576
        m = open("/sys/fs/cgroup/memory.max").read().strip()
        u["mem_limit_mb"] = None if m == "max" else int(m) // 1048576
    except Exception:
        try:
            u["mem_mb"] = int(open("/sys/fs/cgroup/memory/memory.usage_in_bytes").read()) // 1048576
        except Exception:
            pass
    try:
        u["load1"] = round(os.getloadavg()[0], 2)
    except Exception:
        pass
    return u


def fetch_arabic(target=TARGET_CHARS):
    """عينة كبيرة من mC4 العربي عبر HF datasets-server (بدون auth)."""
    out, offset = [], 0
    base = ("https://datasets-server.huggingface.co/rows"
            "?dataset=allenai/c4&config=ar&split=train&length=100")
    while sum(len(x) for x in out) < target and offset < 2_000_000:
        url = f"{base}&offset={offset}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OrcanoxGrow/0.2"})
            d = json.loads(urllib.request.urlopen(req, timeout=60).read())
            rows = [r["row"]["text"] for r in d.get("rows", []) if r.get("row", {}).get("text")]
            if not rows:
                break
            out.extend(rows)
            offset += len(rows)
            if offset % 1000 == 0:
                print(f"mc4: {offset} rows, {sum(len(x) for x in out)} chars", flush=True)
            time.sleep(0.15)
        except Exception as e:
            print("mc4-warn:", e, flush=True)
            time.sleep(3)
    return "".join(out)


def load_corpus():
    if os.path.exists(CORPUS_PATH):
        print("corpus: cache hit", flush=True)
        with open(CORPUS_PATH, encoding="utf-8") as f:
            return f.read()
    text = fetch_arabic()
    tmp = CORPUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, CORPUS_PATH)
    return text


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
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool), diagonal=1)
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
        loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))
        return logits, loss


@torch.no_grad()
def generate(model, prompt, n=100, temp=0.8, topk=40, seed=1234):
    was_training = model.training
    model.eval()
    g = torch.Generator().manual_seed(seed)
    ids = list(prompt.encode("utf-8"))[-model.block:]
    idx = torch.tensor([ids], dtype=torch.long)
    for _ in range(n):
        logits, _ = model(idx[:, -model.block:])
        l = logits[0, -1] / temp
        v, _ = torch.topk(l, min(topk, l.size(-1)))
        l[l < v[-1]] = -float("inf")
        nxt = torch.multinomial(F.softmax(l, -1), 1, generator=g)
        idx = torch.cat([idx, nxt.view(1, 1)], 1)
    if was_training:
        model.train()
    return bytes(idx[0, len(ids):].tolist()).decode("utf-8", "replace")


def save_ckpt(model, opt, steps, seen, elapsed):
    tmp = CKPT_PATH + ".tmp"
    torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                "steps": steps, "seen": seen, "elapsed": elapsed,
                "rng": torch.get_rng_state()}, tmp)
    os.replace(tmp, CKPT_PATH)


def main():
    res = {"threads": THREADS, "train_seconds": TRAIN_SECONDS, "stage": "starting"}
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        t0 = time.time()
        text = load_corpus()
        res["chars_ar"] = len(text)
        res["fetch_seconds"] = round(time.time() - t0, 1)
        if len(text) < 1_000_000:
            res["stage"] = "failed"; res["error"] = f"data too small: {len(text)}"
            report(res); return

        data = torch.tensor(list(text.encode("utf-8")), dtype=torch.long)
        res["tokens_bytes"] = int(data.numel())
        n = int(0.98 * data.numel())
        train, val = data[:n], data[n:]
        block, batch = 256, 16

        model = TinyGPT()
        res["params"] = sum(p.numel() for p in model.parameters())
        opt = torch.optim.AdamW(model.parameters(), lr=3e-4)

        def get_batch(src):
            ix = torch.randint(len(src) - block - 1, (batch,))
            x = torch.stack([src[i:i + block] for i in ix])
            y = torch.stack([src[i + 1:i + block + 1] for i in ix])
            return x, y

        @torch.no_grad()
        def val_loss():
            model.eval()
            v = [model(*get_batch(val))[1].item() for _ in range(5)]
            model.train()
            return sum(v) / len(v)

        # استكمال من checkpoint لو موجودة
        steps, seen, prev_elapsed = 0, 0, 0.0
        resumed = False
        if os.path.exists(CKPT_PATH):
            try:
                ck = torch.load(CKPT_PATH, map_location="cpu")
                model.load_state_dict(ck["model"])
                opt.load_state_dict(ck["opt"])
                steps, seen, prev_elapsed = ck["steps"], ck["seen"], ck["elapsed"]
                torch.set_rng_state(ck["rng"])
                resumed = True
                print(f"resumed: step {steps}, {seen} tokens, {prev_elapsed:.0f}s elapsed",
                      flush=True)
            except Exception as e:
                print("ckpt-warn:", e, flush=True)

        res["resumed"] = resumed
        res["elapsed_hours"] = 0
        res["train_hours"] = round(TRAIN_SECONDS / 3600, 2)
        report(res)  # heartbeat: الداتا جاهزة والتدريب بدأ

        model.train()
        t0 = time.time()
        first_loss, last_loss = None, None
        last_ckpt = time.time()
        last_rep = time.time()
        rep_seen, rep_loss = seen, None

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
                save_ckpt(model, opt, steps, seen, now - t0 + prev_elapsed)
                last_ckpt = now
                print(f"ckpt saved: step {steps}", flush=True)

            if now - last_rep >= REPORT_EVERY:
                dt = now - last_rep
                elapsed = now - t0 + prev_elapsed
                payload = {
                    "stage": "running",
                    "resumed": resumed,
                    "params": res["params"],
                    "steps": steps,
                    "tokens_seen": seen,
                    "tokens_per_sec": round((seen - rep_seen) / dt),
                    "tokens_per_sec_avg": round(seen / max(elapsed, 1)),
                    "elapsed_hours": round(elapsed / 3600, 2),
                    "train_hours": round(TRAIN_SECONDS / 3600, 2),
                    "remaining_hours": round((TRAIN_SECONDS - elapsed) / 3600, 2),
                    "epochs_equiv": round(seen / data.numel(), 3),
                    "loss_first": round(first_loss, 4) if first_loss else None,
                    "loss_last": round(last_loss, 4) if last_loss else None,
                    "val_loss": round(val_loss(), 4),
                    "usage": usage(),
                    "sample": f"{PROMPTS[0]} ⇒ {generate(model, PROMPTS[0], 60)}",
                    "checkpoint_step": steps,
                }
                report(payload, tg=False)
                rep_seen = seen
                last_rep = time.time()

        elapsed = time.time() - t0 + prev_elapsed
        save_ckpt(model, opt, steps, seen, elapsed)
        torch.save(model.state_dict(), FINAL_PATH)

        stage = "stopped" if STOP else "done"
        vl = val_loss()
        samples = {} if STOP else {p: generate(model, p, 100) for p in PROMPTS}
        res.update({
            "stage": stage,
            "resumed": resumed,
            "steps": steps,
            "tokens_seen": seen,
            "tokens_per_sec": round(seen / max(elapsed, 1)),
            "elapsed_hours": round(elapsed / 3600, 2),
            "train_hours": round(TRAIN_SECONDS / 3600, 2),
            "epochs_equiv": round(seen / data.numel(), 3),
            "loss_first": round(first_loss, 4) if first_loss else None,
            "loss_last": round(last_loss, 4) if last_loss else None,
            "val_loss": round(vl, 4),
            "random_baseline_loss": round(math.log(256), 3),
            "usage": usage(),
            "model_mb": round(os.path.getsize(FINAL_PATH) / 1048576, 1),
            "samples": samples,
        })
        with open(METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception as e:
        import traceback
        res["stage"] = "failed"; res["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    report(res)


if __name__ == "__main__":
    main()
