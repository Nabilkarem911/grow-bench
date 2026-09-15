"""
طبقة الجهاز — مكان واحد بيتحكم في CPU/GPU + سقوف الأمان.
قواعد:
- DEVICE=cpu | cuda  (افتراضي cpu — مبدأ المشروع: الحكم النهائي على CPU)
- على الكارت: سقف VRAM إلزامي + checkpoint على CPU قبل الحفظ.
- مفيش أي توتر يتعمل من غير device (ده كان باج كسر التدريب على الكارت).
"""
import os

import torch


def pick_device(default="cpu"):
    """يختار الجهاز من البيئة، ويتأكد إنه متاح فعلًا (مش افتراض)."""
    want = (os.environ.get("DEVICE", default) or default).strip().lower()
    if want.startswith("cuda") and not torch.cuda.is_available():
        print(f"[zdev] WARNING: DEVICE={want} لكن cuda غير متاح → رجوع لـ cpu", flush=True)
        want = "cpu"
    return torch.device(want)


def setup(device, threads=None, vram_fraction=None):
    """يضبط الخيوط وسقف الـ VRAM. يرجّع dict للتقارير."""
    info = {"device": str(device), "threads": None, "vram_limit_mb": None}
    if threads:
        torch.set_num_threads(int(threads))
        info["threads"] = int(threads)
    if device.type == "cuda":
        frac = float(vram_fraction if vram_fraction is not None
                     else os.environ.get("VRAM_FRACTION", "0.35"))
        torch.cuda.set_per_process_memory_fraction(frac, device.index or 0)
        props = torch.cuda.get_device_properties(device.index or 0)
        info.update({
            "gpu": props.name,
            "capability": list(torch.cuda.get_device_capability(device.index or 0)),
            "vram_total_mb": round(props.total_memory / 1048576),
            "vram_limit_mb": round(props.total_memory * frac / 1048576),
        })
        torch.cuda.reset_peak_memory_stats()
    return info


def vram_peak_mb(device):
    if device.type != "cuda":
        return None
    return round(torch.cuda.max_memory_allocated() / 1048576)


def cpu_state_dict(model):
    """حفظ آمن: تنزيل الأوزان على CPU الأول (يمنع checkpoint بأجهزة GPU)."""
    return {k: v.detach().cpu() for k, v in model.state_dict().items()}
