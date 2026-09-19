#!/usr/bin/env python3
"""verify_arabic_memory.py — تحقق فعلي من ذاكرة تيتان العربية.

بيتكلم مع Docker عبر الـsocket (من غير docker CLI)، وبيعمل 3 حاجات:
  ١) يشوف نوع عمود embedding_vec في قاعدة البيانات
  ٢) يشغّل اختبار التشابه العربي جوّه حاوية التمثيل نفسها
  ٣) يتأكد إن المتجهات بتتخزن فعلًا

وبيرفع التقرير على GitHub.
"""
import base64
import http.client
import json
import os
import socket
import time
import urllib.request

SOCK = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("AUDIT_REPO", "Nabilkarem911/grow-bench")
PATH_IN_REPO = "results/arabic_memory_verify.log"

OUT = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    OUT.append(line)


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, sock_path):
        super().__init__("localhost")
        self._sock_path = sock_path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(180)
        s.connect(self._sock_path)
        self.sock = s


def dk(method, path, body=None):
    c = UnixHTTP(SOCK)
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Content-Type": "application/json"} if body is not None else {}
    c.request(method, path, body=data, headers=hdr)
    r = c.getresponse()
    raw = r.read()
    c.close()
    try:
        return r.status, json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return r.status, raw.decode("utf-8", "ignore")


def find(pattern, limit=1):
    _, cs = dk("GET", "/containers/json")
    if not isinstance(cs, list):
        return []
    hits = []
    for c in cs:
        names = " ".join(c.get("Names") or [])
        if pattern in names:
            hits.append(c)
    return hits[:limit]


def container_env(cid):
    _, info = dk("GET", f"/containers/{cid}/json")
    env = {}
    for kv in (info.get("Config", {}).get("Env") or []):
        if "=" in kv:
            k, v = kv.split("=", 1)
            env[k] = v
    return env


def run_in(cid, cmd, tty=True):
    """ينفذ أمر جوّه الحاوية ويرجّع المخرجات."""
    code, ex = dk("POST", f"/containers/{cid}/exec",
                  {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": tty})
    if code not in (200, 201) or not isinstance(ex, dict):
        return f"(فشل إنشاء exec: {code} {str(ex)[:120]})"
    eid = ex.get("Id")
    # start
    c = UnixHTTP(SOCK)
    body = json.dumps({"Detach": False, "Tty": tty}).encode()
    c.request("POST", f"/exec/{eid}/start", body=body, headers={"Content-Type": "application/json"})
    r = c.getresponse()
    raw = r.read()
    c.close()
    if tty:
        txt = raw.decode("utf-8", "ignore")
    else:
        # نزيل ترويسات التدفق (8 بايت لكل إطار)
        out = []
        i = 0
        while i + 8 <= len(raw):
            size = int.from_bytes(raw[i + 4:i + 8], "big")
            out.append(raw[i + 8:i + 8 + size].decode("utf-8", "ignore"))
            i += 8 + size
        txt = "".join(out) if out else raw.decode("utf-8", "ignore")
    return txt.strip()


ARABIC_TEST = r'''
import numpy as np
from fastembed import TextEmbedding
m = TextEmbedding()
def vec(t): return list(m.embed([t]))[0]
def cos(x, y): return float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y)))
pairs = [
    ("نفس المعنى",    "الطلب اتأخر وأنا محتاج حل بسرعة",  "أوردري متأخر ومحتاج مساعدة سريعة"),
    ("نفس المعنى ٢",  "اسمي ابراهيم ورقمي 0555123456",     "أنا ابراهيم تليفوني 0555123456"),
    ("موضوع مختلف",   "الطلب اتأخر وأنا محتاج حل بسرعة",  "الطقس النهاردة جميل في ينبع"),
    ("موضوع مختلف ٢", "عايز أشتري لابتوب جديد",            "فاتورة الكهرباء الشهرية"),
]
same, diff = [], []
for label, a, b in pairs:
    s = cos(vec(a), vec(b))
    print(f"  {label:16} {s:.3f}")
    (same if label.startswith("نفس") else diff).append(s)
print()
print(f"  متوسط (نفس المعنى): {np.mean(same):.3f}   المطلوب > 0.75")
print(f"  متوسط (مختلف):      {np.mean(diff):.3f}")
ok = np.mean(same) > 0.75 and np.mean(same) > np.mean(diff) + 0.15
print("  ➜ " + ("نجح ✓" if ok else "فشل ✗"))
'''


def main():
    say("════════ ١) حاويات تيتان ════════")
    _, cs = dk("GET", "/containers/json")
    titans = [c for c in (cs or []) if "titan" in " ".join(c.get("Names") or [])]
    for c in titans:
        say("  ", (c.get("Names") or [""])[0].lstrip("/"), "·", c.get("Status"))
    embeds = [c for c in titans if "embed" in " ".join(c.get("Names") or [])]
    pgs = [c for c in titans if "postgres" in " ".join(c.get("Names") or [])]
    if not embeds:
        say("❌ مفيش حاوية تمثيل!"); return
    emb = embeds[0]
    say("  حاوية التمثيل:", (emb.get("Names") or [""])[0].lstrip("/"))

    say("")
    say("════════ ٢) النموذج والأبعاد ════════")
    say(run_in(emb["Id"], ["python3", "-c",
        "import json,urllib.request;d=json.load(urllib.request.urlopen('http://localhost:8000/health',timeout=30));"
        "print('  الموديل:',d.get('model'));print('  الأبعاد:',d.get('dimensions'))"]))

    say("")
    say("════════ ٣) اختبار العربي الفعلي (الأهم) ════════")
    say(run_in(emb["Id"], ["python3", "-c", ARABIC_TEST]))

    say("")
    say("════════ ٤) قاعدة البيانات ════════")
    if not pgs:
        say("  (مفيش حاوية postgres)"); return
    pg = pgs[0]
    env = container_env(pg["Id"])
    user = env.get("POSTGRES_USER", "postgres")
    dbname = env.get("POSTGRES_DB", "titan")
    q = ("SELECT format_type(a.atttypid,a.atttypmod) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
         "WHERE c.relname='memory_items' AND a.attname='embedding_vec';")
    pw = env.get("POSTGRES_PASSWORD", "")
    base = ["env", f"PGPASSWORD={pw}", "psql", "-U", user, "-d", dbname, "-t", "-A", "-F", "|", "-c"]
    say("  نوع العمود:", run_in(pg["Id"], base + [q], tty=False))
    q2 = "SELECT 'عناصر: ' || COUNT(*)::text || ' · فيهم متجه: ' || COUNT(embedding_vec)::text FROM memory_items;"
    say("  المخزون:", run_in(pg["Id"], base + [q2], tty=False))
    q3 = ("SELECT filename FROM titan_migrations WHERE filename LIKE '%0035%' OR filename LIKE '%0026%' "
          "ORDER BY filename;")
    say("  الترحيلات المطبقة:", run_in(pg["Id"], base + [q3], tty=False))
    q4 = "SELECT 'عدد الجداول: ' || COUNT(*)::text FROM information_schema.tables WHERE table_schema='public';"
    say("  ", run_in(pg["Id"], base + [q4], tty=False))

    say("")
    say("DONE-ARABIC-VERIFY")

    text = "\n".join(OUT)
    if not TOKEN:
        print("(مفيش توكن — التقرير مطبوع بس)"); return
    api = f"https://api.github.com/repos/{REPO}/contents/{PATH_IN_REPO}"
    hdr = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
           "User-Agent": "fawkes"}
    sha = None
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60))
        sha = d.get("sha")
    except Exception:
        pass
    body = {"message": "Arabic memory verification", "content": base64.b64encode(text.encode()).decode()}
    if sha:
        body["sha"] = sha
    r = json.load(urllib.request.urlopen(urllib.request.Request(api, data=json.dumps(body).encode(),
                                                                headers=hdr, method="PUT"), timeout=90))
    print("✅ اترفع:", r.get("content", {}).get("path"))


def upload():
    """رفع التقرير — بيتم دايمًا حتى لو حصل خطأ."""
    text = "\n".join(OUT)
    if not TOKEN:
        print("(مفيش توكن)"); return
    api = f"https://api.github.com/repos/{REPO}/contents/{PATH_IN_REPO}"
    hdr = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
           "User-Agent": "fawkes"}
    sha = None
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60))
        sha = d.get("sha")
    except Exception:
        pass
    body = {"message": "Arabic memory verification", "content": base64.b64encode(text.encode()).decode()}
    if sha:
        body["sha"] = sha
    r = json.load(urllib.request.urlopen(urllib.request.Request(api, data=json.dumps(body).encode(),
                                                                headers=hdr, method="PUT"), timeout=90))
    print("✅ اترفع:", r.get("content", {}).get("path"))


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception as e:
        say("🚨 خطأ:", repr(e)[:400])
        say(traceback.format_exc()[-1500:])
    finally:
        say("DONE-ARABIC-VERIFY")
        try:
            upload()
        except Exception as e:
            print("🚨 فشل الرفع:", repr(e)[:200])
