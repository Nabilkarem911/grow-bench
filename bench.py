"""
م0 — قياس سرعة التدريب الحقيقية على سيرفر نبيل (CPU فقط)
المخرج: كلمات/ثانية + تقدير الأقصى الممكن.
خفيف عن قصد: 2 threads فقط + مدة محدودة + بدون كارت شاشة.
"""
import json, math, os, sys, time, urllib.parse, urllib.request

import torch, torch.nn as nn, torch.nn.functional as F

TRAIN_SECONDS = int(os.environ.get("TRAIN_SECONDS", "240"))
THREADS = int(os.environ.get("THREADS", "2"))
TARGET_CHARS = int(os.environ.get("TARGET_CHARS", "1200000"))
REPORT_URL = os.environ.get("REPORT_URL", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

torch.set_num_threads(THREADS)


def report(payload: dict):
    """يطلّع النتيجة بره الكونتينر: ntfy + تيليجرام."""
    body = json.dumps(payload, ensure_ascii=False)
    print("REPORT " + body, flush=True)
    if REPORT_URL:
        try:
            req = urllib.request.Request(REPORT_URL, data=body.encode("utf-8"),
                                         headers={"Title": "grow-bench M0"})
            urllib.request.urlopen(req, timeout=20)
        except Exception as e:
            print("report-warn:", e, flush=True)
    if TG_TOKEN and TG_CHAT:
        try:
            f = lambda k, d="—": (f"{payload.get(k):,}" if isinstance(payload.get(k), (int, float)) else d)
            txt = ("🧪 grow-bench M0 — قياس تدريب على CPU\n"
                   f"params: {f('params')}\n"
                   f"tokens/sec: {f('tokens_per_sec')}\n"
                   f"loss: {f('loss_first')} → {f('loss_last')} (عشوائي {f('random_baseline_loss')})\n"
                   f"ساعات لكل 100M توكن: {f('hours_per_100M_tokens')}\n"
                   f"مرحلة: {payload.get('stage')} · {payload.get('error','')}"[:900])
            data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": txt,
                                           "parse_mode": "Markdown"}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                   data=data, timeout=20)
        except Exception as e:
            print("telegram-warn:", e, flush=True)


def fetch_arabic(target=TARGET_CHARS):
    """نص عربي حقيقي: ويكيبيديا العربية باحترام قواعدها (طلب/ثانية)، مع بدائل."""
    out, calls, last = [], 0, 0.0

    def get(url, hdrs):
        nonlocal last
        wait = 1.2 - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.time()
        req = urllib.request.Request(url, headers=hdrs)
        return urllib.request.urlopen(req, timeout=30).read()

    while sum(len(x) for x in out) < target and calls < 120:
        calls += 1
        u = ("https://ar.wikipedia.org/w/api.php?action=query&generator=random"
             "&grnnamespace=0&grnlimit=20&prop=extracts&explaintext=1&format=json")
        try:
            d = json.loads(get(u, {"User-Agent": "OrcanoxGrowBench/0.1 (research; contact@orcanox.xyz)"}))
            for pg in d.get("query", {}).get("pages", {}).values():
                out.append(pg.get("extract", ""))
        except Exception as e:
            print("wiki-warn:", e, flush=True)

    # لو لسه قليل: نكمّل من نصوص عربية أخرى
    if sum(len(x) for x in out) < target // 2:
        for extra in [
            "https://ar.wikisource.org/w/api.php?action=query&generator=random&grnnamespace=0&grnlimit=20&prop=extracts&explaintext=1&format=json",
            "https://ar.wikinews.org/w/api.php?action=query&generator=random&grnnamespace=0&grnlimit=20&prop=extracts&explaintext=1&format=json",
        ]:
            for _ in range(25):
                try:
                    d = json.loads(get(extra, {"User-Agent": "OrcanoxGrowBench/0.1 (research)"}))
                    for pg in d.get("query", {}).get("pages", {}).values():
                        out.append(pg.get("extract", ""))
                except Exception as e:
                    print("extra-warn:", e, flush=True)
                if sum(len(x) for x in out) >= target:
                    break
    return "".join(out)


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


def main():
    res = {"threads": THREADS, "train_seconds": TRAIN_SECONDS, "stage": "starting"}
    try:
        import urllib.parse  # noqa
        t0 = time.time()
        text = fetch_arabic()
        res["chars_ar"] = len(text)
        res["fetch_seconds"] = round(time.time() - t0, 1)
        if len(text) < 250_000:
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

        model.train()
        t0, steps, seen, first_loss, last_loss = time.time(), 0, 0, None, None
        while time.time() - t0 < TRAIN_SECONDS:
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
        train_s = time.time() - t0

        model.eval()
        with torch.no_grad():
            vl = [model(*get_batch(val))[1].item() for _ in range(5)]
        tps = max(1, round(seen / train_s))
        res.update({
            "stage": "done",
            "steps": steps,
            "train_seconds_actual": round(train_s, 1),
            "tokens_seen": seen,
            "tokens_per_sec": tps,
            "loss_first": round(first_loss, 4) if first_loss else None,
            "loss_last": round(last_loss, 4) if last_loss else None,
            "val_loss": round(sum(vl) / len(vl), 4),
            "random_baseline_loss": round(math.log(256), 3),
            "hours_per_100M_tokens": round(100_000_000 / tps / 3600, 2),
            "hours_per_500M_tokens": round(500_000_000 / tps / 3600, 2),
            "sample": text[:300].replace("\n", " "),
        })
    except Exception as e:
        import traceback
        res["stage"] = "failed"; res["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    report(res)


if __name__ == "__main__":
    main()
