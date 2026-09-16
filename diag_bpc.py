"""diag_bpc.py — تشخيص: ليه أرقام «بت/حرف» مختلفة بين القياسين؟ نفس النص، نفس الدالة، 3 موديلات."""
import json, math, os, random, re
os.environ.setdefault("HF_HOME", "F:/projects/grow/hf")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

L2 = math.log(2)
CORPUS = "F:/projects/grow/data/corpus.txt"
MODELS = [("base", "Qwen/Qwen2.5-0.5B"),
          ("armB(مدفّى)", "F:/projects/grow/data/ready/ft_armB"),
          ("grown(مكبَّر+مدفّى)", "F:/projects/grow/data/ready/ft_armA")]
dev = "cuda" if torch.cuda.is_available() else "cpu"
rng = random.Random(7)
raw = open(CORPUS, encoding="utf-8").read()

# نص من نفس التوزيع بطولين مختلفين
def seg(start, n):
    s = raw[start:start + n]
    return re.sub(r"\s+", " ", s).strip()

samples = {"قصير 200 حرف": seg(5000, 200), "طويل 1000 حرف": seg(5000, 1000),
           "من آخر الكوربوس (200)": seg(int(0.99 * len(raw)), 200)}


def bpc(model, tok, text):
    ids = tok(text, return_tensors="pt", add_special_tokens=False).input_ids.to(dev)
    with torch.no_grad():
        out = model(input_ids=ids, labels=ids)
        logits = model(input_ids=ids).logits          # لحساب بدون أول كلمة
    l = float(out.loss.item())
    # بدون أول 8 كلمات (نشيل تأثير بداية النص)
    lp = torch.log_softmax(logits[:, :-1].float(), dim=-1)
    tgt = ids[:, 1:]
    tok_losses = -lp.gather(-1, tgt.unsqueeze(-1)).squeeze(-1)[0]
    l_skip = float(tok_losses[8:].mean().item()) if tok_losses.numel() > 10 else l
    ntok = ids.shape[1]
    return (round(l / L2 * ntok / max(len(text), 1), 3),
            round(l_skip / L2 * ntok / max(len(text), 1), 3), ntok)


print(f"طول النصوص: {[(k, len(v)) for k, v in samples.items()]}\n")
print(f"{'الموديل':22s} | " + " | ".join(f"{k}" for k in samples))
print("-" * 100)
for name, path in MODELS:
    tok = AutoTokenizer.from_pretrained(path)
    m = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float32).to(dev).eval()
    row = []
    for k, txt in samples.items():
        a, b, n = bpc(m, tok, txt)
        row.append(f"{a:.3f}/{b:.3f}")
    print(f"{name:22s} | " + " | ".join(row))
    del m
    torch.cuda.empty_cache()
print("\n(الرقم الأول = بت/حرف بالطريقة العادية | التاني = بدون أول 8 كلمات)")
