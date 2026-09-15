"""
ft_hf_lora.py — تدريب جزئي (LoRA) على الكوربوس العربي بميزانية كلمات محددة.
الغرض: مقارنة عادلة بين موديل جاهز وموديل مكبَّر بنفس مقدار الشغل.
يقرأ: F:/projects/grow/data/corpus.txt (أول 98% تدريب — آخر 2% امتحان).
يطلّع: موديل مدموج + metrics.

الاستخدام:
  python ft_hf_lora.py --model <path_or_id> --tag <name> --tokens <N> --out <dir>
"""
import argparse, json, os, time

os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# يقلّل تفتيت ذاكرة الكارت (موصى به في رسالة الخطأ)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model

CORPUS = "F:/projects/grow/data/corpus.txt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--tokens", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--block", type=int, default=512)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--vram", type=float, default=0.50)
    ap.add_argument("--no-checkpointing", action="store_true")
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cuda":
        torch.cuda.set_per_process_memory_fraction(a.vram)
        torch.cuda.reset_peak_memory_stats()
        torch.backends.cuda.matmul.allow_tf32 = True

    res = {"stage": "ft_lora", "tag": a.tag, "model": a.model, "device": dev,
           "tokens_budget": a.tokens}
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(a.model)
    base = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).to(dev)
    base.config.use_cache = False
    if not a.no_checkpointing:
        # يوفر رام الكارت على حساب شغل إضافي — وده الرصيد اللي عندنا
        base.gradient_checkpointing_enable()
        base.enable_input_require_grads()
        res["gradient_checkpointing"] = True
    p_base = sum(p.numel() for p in base.parameters())

    lcfg = LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, bias="none",
                      task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                      "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(base, lcfg)
    n_train = sum(p.numel() for p in model.parameters() if p.requires_grad)
    res["params_base"] = p_base
    res["params_trainable"] = n_train

    text = open(CORPUS, encoding="utf-8").read()
    train_txt = text[:int(0.98 * len(text))]
    chunks = [train_txt[i:i + 200000] for i in range(0, len(train_txt), 200000)]
    ids = torch.cat([tok(c, return_tensors="pt").input_ids[0] for c in chunks])
    res["train_tokens_available"] = int(ids.numel())
    res["vocab"] = len(tok)

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=a.lr, betas=(0.9, 0.95), weight_decay=0.0)
    import math
    step_tokens = a.batch * a.block * a.accum
    total_steps = max(1, math.ceil(a.tokens / step_tokens) + 1)   # +1 أمان (الباج اللي وقع قبل كده)
    res["total_steps_planned"] = total_steps
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr,
                                                total_steps=total_steps, pct_start=0.03)
    model.train()
    seen, step, losses, t1 = 0, 0, [], time.time()
    while seen < a.tokens:
        opt.zero_grad(set_to_none=True)
        for _ in range(a.accum):
            ix = torch.randint(len(ids) - a.block - 1, (a.batch,))
            x = torch.stack([ids[i:i + a.block] for i in ix]).to(dev)
            y = torch.stack([ids[i + 1:i + a.block + 1] for i in ix]).to(dev)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=(dev == "cuda")):
                out = model(input_ids=x, labels=y)
                loss = out.loss / a.accum
            loss.backward()
            seen += a.batch * a.block
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        sched.step()
        step += 1
        if step % 100 == 0:          # حفظ دوري — عشان أي وقع ميتكلّفش الساعات اللي فاتت
            try:
                os.makedirs(a.out, exist_ok=True)
                model.save_pretrained(os.path.join(a.out, "lora_ckpt"), safe_serialization=True)
            except Exception as e:
                print(f"ckpt-warn: {e}", flush=True)
        if step % 20 == 0 or seen >= a.tokens:
            l = float(loss.item()) * a.accum
            losses.append({"step": step, "seen": seen, "loss": round(l, 4),
                           "lr": round(sched.get_last_lr()[0], 7),
                           "tps": round(seen / (time.time() - t1), 0)})
            print(f"ft {a.tag}: step {step} | كلمات {seen:,} | loss {l:.4f} | "
                  f"{seen/(time.time()-t1):,.0f} كلمة/ث", flush=True)

    res["tokens_seen"] = seen
    res["steps"] = step
    res["loss_first"] = losses[0]["loss"] if losses else None
    res["loss_last"] = losses[-1]["loss"] if losses else None
    res["elapsed_seconds"] = round(time.time() - t1, 1)
    res["tokens_per_sec"] = round(seen / (time.time() - t1), 0)
    res["loss_trace"] = losses[-8:]
    res["compute_proxy_tokens_x_params"] = seen * p_base
    if dev == "cuda":
        res["vram_peak_mb"] = round(torch.cuda.max_memory_allocated() / 1048576)

    merged = model.merge_and_unload()
    os.makedirs(a.out, exist_ok=True)
    merged.to("cpu").save_pretrained(a.out, safe_serialization=True)
    tok.save_pretrained(a.out)
    res["saved_to"] = a.out
    res["stage"] = "done"
    res["total_seconds"] = round(time.time() - t0, 1)
    os.makedirs("F:/projects/grow/data/results", exist_ok=True)
    json.dump(res, open(f"F:/projects/grow/data/results/ft_{a.tag}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("FT_RESULT " + json.dumps(res, ensure_ascii=False)[:1200], flush=True)


if __name__ == "__main__":
    main()
