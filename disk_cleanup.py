#!/usr/bin/env python3
"""تنظيف مساحة السيرفر — يمسح بقايا البطولات فقط.

قواعد الأمان (ممنوع تُخترق):
  1. الموديل الشغال على الخدمة لا يُمسح (يُقرأ من LLM_MODEL/knowledge).
  2. bge-m3 (خدمة التمثيل) لا يُمسح.
  3. /data/llama (بنية llama.cpp) و /data/results (النتايج) لا تُمسح.
  4. مفيش حذف لمشاريع نبيل التانية (صور Docker بتاعتها) — بس كاش البناء بتاعنا.
"""
import http.client, json, os, socket, subprocess

SOCK = "/var/run/docker.sock"
MOE = "/data/moe"

# ✅ اللي بنحتفظ بيه بالاسم (شغال فعلًا)
KEEP = {
    "bge-m3-f16.gguf",            # خدمة التمثيل
    "Qwen3-1.7B-Q4_K_M.gguf",     # الموديل الشغال على llm.orcanox.xyz
}


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p

    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(600); sk.connect(s._p); s.sock = sk


def dk(m, p, b=None):
    c = U(SOCK)
    c.request(m, p, body=json.dumps(b).encode() if b is not None else None,
              headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); raw = r.read(); c.close()
    try:
        return json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return raw.decode("utf-8", "ignore")


def sh(cmd, t=900):
    try:
        r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, timeout=t)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return "(فشل: %s)" % str(e)[:80]


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024
    return "%.1f PB" % n


print("=== 0) قبل أي حاجة: الموديل الشغال فعلًا على الخدمة ===")
try:
    c = U(SOCK)
    c.request("GET", "/containers/json")
    cs = json.loads(c.getresponse().read().decode("utf-8", "ignore")); c.close()
    names = [n for ct in cs for n in (ct.get("Names") or [])]
    print("  حاويات:", ", ".join(n.lstrip("/") for n in names if "grow" in n)[:200])
except Exception as e:
    print("  ", str(e)[:80])
print("  نموذج llm الحالي:", sh("curl -s --max-time 20 http://llm:8080/props 2>/dev/null | head -c 300 || echo '(مش متاح من هنا)'")[:200])

print("\n=== 1) قبل ===")
print(sh("df -h /data | tail -2"))

print("\n=== 2) اللي هنمسحه (بقايا البطولات) ===")
if not os.path.isdir(MOE):
    print("  ⚠️ المجلد مش موجود"); raise SystemExit
victims, total = [], 0
for f in sorted(os.listdir(MOE)):
    p = os.path.join(MOE, f)
    if not os.path.isfile(p):
        continue
    sz = os.path.getsize(p)
    if f in KEEP:
        print("   ✅ بنحتفظ  %8s  %s" % (human(sz), f))
    else:
        victims.append(f)
        total += sz
        print("   🗑️ هنمسح   %8s  %s" % (human(sz), f))
print("  الإجمالي الممسوح من الموديلات: %s · عدد: %d" % (human(total), len(victims)))

# ملفات تانية من تجارب التدريب (مش موديلات شغالة)
extra = ["/data/qwen2.5-0.5b-instruct-fp16.gguf", "/data/qwen2.5-0.5b-instruct-q4_k_m.gguf",
         "/data/corpus.txt", "/data/model_final.pt", "/data/checkpoint.pt"]
extra_exist = [p for p in extra if os.path.exists(p)]
ex_size = sum(os.path.getsize(p) for p in extra_exist)
ex_dirs = [d for d in ("/data/hf", "/data/ft", "/data/factory") if os.path.isdir(d)]
print("  ملفات تجارب: %s (%d ملف)" % (human(ex_size), len(extra_exist)))
print("  مجلدات تجارب: %s" % ", ".join(ex_dirs))

print("\n=== 3) بنمسح ===")
for f in victims:
    print("   ", sh("rm -f '%s' && echo 'اتمسح: %s'" % (os.path.join(MOE, f), f))[:80], end="")
for p in extra_exist:
    sh("rm -f '%s'" % p)
sh("rm -rf /data/hf")
print("  ✅ خلص حذف الموديلات والملفات")

print("\n=== 4) كاش البناء والصور المعلّقة (تبعنا) ===")
print("  ", sh("echo prune", t=30))
try:
    c = U(SOCK)
    c.request("POST", "/build/prune", body=b"", headers={"Content-Type": "application/json"})
    print("  كاش البناء:", c.getresponse().read().decode()[:200]); c.close()
except Exception as e:
    print("  كاش البناء: (فشل)", str(e)[:80])
try:
    c = U(SOCK)
    c.request("POST", "/images/prune?filters=%7B%22dangling%22%3A%7B%22true%22%3Atrue%7D%7D", body=b"",
              headers={"Content-Type": "application/json"})
    print("  صور معلّقة:", c.getresponse().read().decode()[:300]); c.close()
except Exception as e:
    print("  صور معلّقة: (فشل)", str(e)[:80])

print("\n=== 5) بعد ===")
print(sh("df -h /data | tail -2"))
print("\n=== 6) تأكيد إن اللي شغال لسه موجود ===")
print(sh("ls -lh /data/moe/ 2>/dev/null"))
print(sh("ls /data/llama 2>/dev/null | head -3"))
print("\nDONE-DISK-CLEAN")
