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
    ("30B-Q3_K_M", "https://huggingface.co/bartowski/Qwen_Qwen3-30B-A3B-GGUF/resolve/main/Qwen_Qwen3-30B-A3B-Q3_K_M.gguf", f"{MOE}/30B-Q3_K_M.gguf"),
    ("Qwen3-4B", None, f"{MOE}/Qwen3-4B-Q4_K_M.gguf"),
    ("Qwen3-1.7B", "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf", f"{MOE}/Qwen3-1.7B-Q4_K_M.gguf"),
    ("Granite-4.0-1B", "https://huggingface.co/ibm-granite/granite-4.0-1b-GGUF/resolve/main/granite-4.0-1b-Q4_K_M.gguf", f"{MOE}/granite-4.0-1b-Q4_K_M.gguf"),
    ("LFM2.5-1.2B", "https://huggingface.co/bartowski/LiquidAI_LFM2.5-1.2B-Instruct-GGUF/resolve/main/LiquidAI_LFM2.5-1.2B-Instruct-Q4_K_M.gguf", f"{MOE}/LFM2.5-1.2B-Q4_K_M.gguf"),
    ("Ling-mini-2.0", "https://huggingface.co/bartowski/inclusionAI_Ling-mini-2.0-GGUF/resolve/main/inclusionAI_Ling-mini-2.0-Q4_K_M.gguf", f"{MOE}/Ling-mini-2.0-Q4_K_M.gguf"),
    ("Qwen3.5-4B", "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf", f"{MOE}/Qwen3.5-4B-Q4_K_M.gguf"),
]

PROMPTS = [
    ("كتابة عربية", "اكتبلي رسالة واتساب قصيرة لعميل اتأخر عليه الأوردر، بالعربي."),
    ("برمجة", "اكتب دالة بايثون تتحقق إذا كان الرقم أولي، واشرحها باختصار."),
    ("استدلال", "عندي 3 صناديق: الأول فيه 5 تفاحات، والتاني ضعف الأول، والتالت فيه نصف مجموع الأول والتاني. كام تفاحة الإجمالي؟ اشرح خطوة بخطوة."),
    ("JSON", "صنّف الرسالة دي ورجّع JSON فقط بالمفاتيح type وurgency. الرسالة: فيه تأخير كبير في أوردري ومحتاج حل بسرعة."),
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


def main():
    # 0) المكتبات الأساسية — من غيرها ملفات llama مش هتقوم (libgomp.so.1)
    sh("apt-get update -qq && apt-get install -y -qq libgomp1 libstdc++6 ca-certificates procps >/dev/null 2>&1", timeout=600)
    srv = find_bin("llama-server")
    if not srv:
        raise RuntimeError("llama-server مش موجود")
    ld = os.path.dirname(srv)
    print("llama-server:", srv)

    rep = {"when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "note": "قياس حقيقي على ARM64 · 4 أنوية · 3 خيوط · بلا كارت شاشة · بلا تفكير (-rea off)",
           "prompts": [p[0] for p in PROMPTS], "models": {}}
    save(rep)

    for name, url, path in MODELS:
        entry = {"results": {}}
        ok, note = ensure(path, url)
        entry["download"] = note
        if not ok:
            entry["error"] = note
            rep["models"][name] = entry
            save(rep)
            continue
        entry["size_gb"] = round(os.path.getsize(path) / 2**30, 2)
        print(f"\n===== {name} ({entry['size_gb']} جيجا) =====")

        # ⚠️ مهم: نقتل أي خادم قديم — وإلا الموديل القديم يفضل يرد ونقيس غلط
        kill_servers()

        cmd = (f'LD_LIBRARY_PATH="{ld}:{LLAMA}:$LD_LIBRARY_PATH" "{srv}" -m "{path}" -ngl 0 -t 3 '
               f'-c 2048 -nr -rea off --no-warmup --host 127.0.0.1 --port {PORT}')
        logp = f"/data/results/arena_srv_{name.replace('/','_')}.log"
        log = open(logp, "w")
        proc = subprocess.Popen(cmd, shell=True, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        avail = None
        try:
            with open("/proc/meminfo") as f:
                for ln in f:
                    if ln.startswith("MemAvailable"):
                        avail = int(ln.split()[1]) // 1024
                        break
        except Exception:
            pass
        entry["mem_available_mb"] = avail
        load = wait_ready()
        entry["load_seconds"] = round(load, 1) if load else None
        if load is None:
            log.flush()
            tail = ""
            try:
                tail = open(logp, encoding="utf-8", errors="replace").read()[-900:]
            except Exception:
                pass
            entry["error"] = "الخادم ماقامش"
            entry["server_log_tail"] = tail
            sh("pkill -9 -f llama-server")
            rep["models"][name] = entry
            save(rep)
            continue

        # ⚠️ تحقق إلزامي: هل الخادم فعلًا بيخدم الموديل المطلوب؟ (مش موديل قديم عالق)
        try:
            props = api("/props", timeout=30)
            served = props.get("model_path", "")
            entry["served_model"] = served
            if os.path.basename(served) != os.path.basename(path):
                entry["error"] = f"قياس باطل: الخادم بيخدم {served} مش {path}"
                print("  ❌ انتبه:", entry["error"])
                sh("pkill -9 -f llama-server")
                rep["models"][name] = entry
                save(rep)
                continue
            print(f"  ✅ الموديل الصحيح: {os.path.basename(served)}")
        except Exception as e:
            entry["props_error"] = str(e)[:120]
        log.close()
        print(f"  قام في {load:.0f} ثانية")

        try:
            for ptitle, prompt in PROMPTS:
                t0 = time.time()
                try:
                    d = api("/v1/chat/completions", {"messages": [{"role": "user", "content": prompt}],
                                                     "max_tokens": 300, "temperature": 0.4})
                    el = time.time() - t0
                    u = d.get("usage", {})
                    ct = u.get("completion_tokens") or 0
                    entry["results"][ptitle] = {
                        "tok_s": round(ct / el, 1) if el else None,
                        "seconds": round(el, 1),
                        "tokens": ct,
                        "text": (d["choices"][0]["message"].get("content") or "")[:1200],
                    }
                    print(f"  [{ptitle}] {ct} كلمة · {ct/el:.1f} كلمة/ث")
                except Exception as e:
                    entry["results"][ptitle] = {"error": str(e)[:120]}
                    print(f"  [{ptitle}] خطأ: {str(e)[:60]}")
                save(rep)
        finally:
            kill_servers()
        rep["models"][name] = entry
        save(rep)

    print("\n=== خلصت البطولة ===")
    for name, e in rep["models"].items():
        sp = [v.get("tok_s") for v in (e.get("results") or {}).values() if v.get("tok_s")]
        if sp:
            print(f"  {name:<16} {e.get('size_gb')} جيجا · {sum(sp)/len(sp):.1f} كلمة/ث")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        save({"error": f"{type(e).__name__}: {str(e)[:300]}"})
