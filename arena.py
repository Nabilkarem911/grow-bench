#!/usr/bin/env python3
"""arena.py — بطولة حقيقية بين الموديلات على معالج السيرفر (بدون كارت).

لكل موديل: نشغّل llama-server (تحميل مرة واحدة) → نرسل **نفس الأسئلة** → نقيس
السرعة والوقت والنص الكامل → نقفل الخادم. (أسرع بكتير من إعادة تحميل الموديل لكل سؤال)

النتيجة: /data/results/arena.json (بيانات بحثية — مفيش أي بيانات عملاء)
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

R = "/data/results"
MOE = "/data/moe"
LLAMA = "/data/llama"
PORT = 8099

MODELS = [
    ("ERNIE-4.5-21B-A3B", "https://huggingface.co/bartowski/baidu_ERNIE-4.5-21B-A3B-PT-GGUF/resolve/main/baidu_ERNIE-4.5-21B-A3B-PT-Q4_K_M.gguf", f"{MOE}/ERNIE-4.5-21B-A3B-Q4_K_M.gguf"),
    ("Qwen3-1.7B", "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf", f"{MOE}/Qwen3-1.7B-Q4_K_M.gguf"),
]

PROMPTS = [
    ("كتابة عربية", "اكتبلي رسالة واتساب قصيرة لعميل اتأخر عليه الأوردر، بالعربي."),
    ("برمجة", "اكتب دالة بايثون تتحقق إذا كان الرقم أولي، واشرحها باختصار."),
    ("استدلال", "عندي 3 صناديق: الأول فيه 5 تفاحات، والتاني ضعف الأول، والتالت فيه نصف مجموع الأول والتاني. كام تفاحة الإجمالي؟ اشرح خطوة بخطوة."),
    ("JSON", "صنّف الرسالة دي ورجّع JSON فقط بالمفاتيح type وurgency. الرسالة: فيه تأخير كبير في أوردري ومحتاج حل بسرعة."),
    ("عربي - رد على شكوى", "عميل بيقول: «فيه تأخير كبير في أوردري ومحتاج حل بسرعة». اكتبلي رد مهني على الرسالة دي، بالعربي."),
]


def sh(cmd, timeout=1800):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def find_bin(name):
    return sh(f"find {LLAMA} -name {name} -type f 2>/dev/null | head -1").stdout.strip()


def _dl(url, path):
    """تنزيل مع استكمال من حيث توقف (بدون curl — الصورة النحيفة مفيهاش)."""
    pos = os.path.getsize(path) if os.path.exists(path) else 0
    hdr = {"User-Agent": "arena"}
    if pos:
        hdr["Range"] = f"bytes={pos}-"
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb" if r.status == 200 else "ab") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)


def ensure(path, url):
    if os.path.exists(path) and os.path.getsize(path) > 50_000_000:
        return True, "موجود"
    if not url:
        return False, "مفيش رابط"
    for i in range(1, 7):
        try:
            _dl(url, path)
        except Exception as e:
            print(f"  محاولة {i} فشلت: {str(e)[:90]}")
        if os.path.exists(path) and os.path.getsize(path) > 50_000_000:
            return True, f"اتنزّل ({os.path.getsize(path)/2**30:.2f} جيجا)"
        time.sleep(5)
    return False, "فشل التنزيل"


def api(path, body=None, timeout=900):
    url = f"http://127.0.0.1:{PORT}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def wait_ready(deadline=420):
    t0 = time.time()
    while time.time() - t0 < deadline:
        try:
            api("/health", timeout=5)
            return time.time() - t0
        except Exception:
            time.sleep(3)
    return None


def kill_servers():
    """نقتل أي خادم llama عالق — من بايثون مباشرة (pkill مش مضمون في الصورة النحيفة)."""
    sh("pkill -9 -f llama-server 2>/dev/null")
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().decode("utf-8", "replace")
                if "llama-server" in cmd:
                    os.kill(int(pid), 9)
                    print(f"  قتلنا خادم قديم (pid {pid})", flush=True)
            except Exception:
                pass
    except Exception:
        pass
    time.sleep(3)


def save(rep):
    os.makedirs(R, exist_ok=True)
    with open(f"{R}/arena.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)

# ⚠️ التنفيذ وقت التشغيل فقط (مش وقت الاستيراد) — عشان capability_arena
#    يقدر يستورد الدوال من هنا من غير مرجع دائري.
if __name__ == "__main__":
    exec(open("/app/capability_arena.py", encoding="utf-8").read())
