"""
cpu_bench_server.py — يقيس على المعالج بتاع السيرفر (بدون كارت شاشة):
سرعة موديل 0.5B قبل وبعد الضغط لـ8 بت. بيبعت النتيجة على ntfy + تيليجرام.
"""
import json, math, os, time, urllib.request

os.environ.setdefault("HF_HOME", "/data/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = os.environ.get("BENCH_MODEL", "Qwen/Qwen2.5-0.5B")
THREADS = int(os.environ.get("THREADS", "4"))
RESULTS = os.environ.get("RESULTS_DIR", "/data/results")
PROMPTS = ["في صباح اليوم التالي", "اللغة العربية هي", "قال العالم"]


def notify(title, msg, tags="white_check_mark"):
    url = os.environ.get("REPORT_URL", "").strip()
    if url:
        try:
            urllib.request.urlopen(urllib.request.Request(
                url, data=msg.encode("utf-8"),
                headers={"Title": title.encode("ascii", "ignore").decode(), "Tags": tags}), timeout=20)
        except Exception as e:
            print("ntfy-warn:", e, flush=True)
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if tok and chat:
        try:
            body = json.dumps({"chat_id": chat, "text": msg[:3900], "parse_mode": "HTML"}).encode()
            urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage", data=body,
                headers={"Content-Type": "application/json"}), timeout=25)
        except Exception as e:
            print("tg-warn:", e, flush=True)


def speed(model, tok, n=40):
    rates = []
    model.eval()
    with torch.no_grad():
        for p in PROMPTS:
            enc = tok(p, return_tensors="pt").input_ids
            t = time.time()
            o = model.generate(enc, max_new_tokens=n, do_sample=True, temperature=0.8,
                               top_p=0.95, pad_token_id=tok.eos_token_id, use_cache=True)
            rates.append((o.shape[1] - enc.shape[1]) / (time.time() - t))
    return round(sum(rates) / len(rates), 1)


def main():
    torch.set_num_threads(THREADS)
    res = {"stage": "cpu_bench_server", "model": MODEL, "threads": THREADS,
           "host": os.uname().nodename if hasattr(os, "uname") else "server",
           "torch": torch.__version__}
    print(f"بدء القياس على {THREADS} خيوط — {MODEL}", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL)
    t0 = time.time()
    m = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32).eval()
    res["load_seconds"] = round(time.time() - t0, 1)
    res["params"] = sum(p.numel() for p in m.parameters())
    res["size_mb"] = round(res["params"] * 4 / 1048576, 1)
    res["fp32_tok_per_sec"] = speed(m, tok)
    print(f"fp32: {res['fp32_tok_per_sec']} كلمة/ث", flush=True)

    q = torch.ao.quantization.quantize_dynamic(m, {torch.nn.Linear}, dtype=torch.qint8).eval()
    res["int8_tok_per_sec"] = speed(q, tok)
    res["speedup_x"] = round(res["int8_tok_per_sec"] / max(res["fp32_tok_per_sec"], 1e-9), 2)
    print(f"int8: {res['int8_tok_per_sec']} كلمة/ث (×{res['speedup_x']})", flush=True)

    with torch.no_grad():
        enc = tok("في صباح اليوم التالي", return_tensors="pt").input_ids
        o = q.generate(enc, max_new_tokens=40, do_sample=True, temperature=0.8, top_p=0.95,
                       pad_token_id=tok.eos_token_id)
        res["sample_ar"] = tok.decode(o[0], skip_special_tokens=True)

    os.makedirs(RESULTS, exist_ok=True)
    json.dump(res, open(f"{RESULTS}/cpu_server.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    msg = (f"⚙️ قياس السيرفر (بدون كارت شاشة)\n"
           f"الموديل: {MODEL} ({res['size_mb']:.0f} ميجا)\n"
           f"خيوط: {THREADS}\n"
           f"fp32: {res['fp32_tok_per_sec']} كلمة/ث\n"
           f"8 بت: {res['int8_tok_per_sec']} كلمة/ث (×{res['speedup_x']})\n"
           f"عينة: {res['sample_ar'][:120]}")
    notify("grow cpu-bench server", msg)
    print("SERVER_BENCH " + json.dumps(res, ensure_ascii=False)[:900], flush=True)
    print("[" + json.dumps(res, ensure_ascii=False) + "]")


if __name__ == "__main__":
    main()
