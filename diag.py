#!/usr/bin/env python3
"""تشخيص: ليه سكربت التقييم مابيرفعش؟ نقرا لوجات الحاوية نفسها + نجرب طرف منه."""
import http.client, json, os, socket, subprocess

SOCK = "/var/run/docker.sock"


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(120); sk.connect(s._p); s.sock = sk


def dk(m, p, b=None, raw=False):
    c = U(SOCK)
    c.request(m, p, body=json.dumps(b).encode() if b is not None else None,
              headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); data = r.read(); c.close()
    if raw:
        return data
    try:
        return json.loads(data.decode("utf-8", "ignore"))
    except Exception:
        return data.decode("utf-8", "ignore")


def logs_of(cid, tail=150):
    raw = dk("GET", "/containers/%s/logs?stdout=1&stderr=1&tail=%d" % (cid, tail), raw=True)
    out, i = [], 0
    while i + 8 <= len(raw):
        n = int.from_bytes(raw[i + 4:i + 8], "big")
        if n > len(raw) - i - 8:
            break
        out.append(raw[i + 8:i + 8 + n].decode("utf-8", "ignore")); i += 8 + n
    return "".join(out) if out else raw.decode("utf-8", "ignore")


cs = dk("GET", "/containers/json")
me = [c for c in (cs or []) if "grow-bench" in " ".join(c.get("Names") or []) and "sysinfo" in " ".join(c.get("Names") or [])]

print("=== 1) لوجات حاوية الفحص (نفسها) ===")
if me:
    lg = logs_of(me[0]["Id"], 120)
    for line in lg.splitlines()[-70:]:
        print("  " + line[:250])
else:
    print("  ⚠️ مش لاقي حاوية الفحص")

print("\n=== 2) هل السكربت موجود؟ ===")
print("  comprehensive.py:", "موجود" if os.path.exists("/app/comprehensive.py") else "❌ مش موجود")
print("  run_comprehensive.sh:", "موجود" if os.path.exists("/app/run_comprehensive.sh") else "❌ مش موجود")
print("  task.txt:", open("/app/task.txt").read().strip() if os.path.exists("/app/task.txt") else "❌")

print("\n=== 3) نجرب نستورد السكربت (نشوف فيه خطأ؟) ===")
r = subprocess.run(["python3", "-c", "import ast,sys; ast.parse(open('/app/comprehensive.py',encoding='utf-8').read()); print('✅ السكربت سليم لغويًا')"],
                   capture_output=True, text=True, timeout=60)
print("  " + (r.stdout or r.stderr).strip()[:300])

print("\n=== 4) نجرب أول خطوة منه فعليًا (الاتصال بالويبهوك) ===")
r2 = subprocess.run(["python3", "-c", """
import json,urllib.request,time
W='https://titan.orcanox.xyz/telegram/webhook'; CHAT=495185511
body={'update_id':99001,'message':{'message_id':99001,'from':{'id':CHAT,'is_bot':False,'first_name':'Nabil'},'chat':{'id':CHAT,'type':'private'},'date':int(time.time()),'text':'اختبار تشخيصي'}}
rq=urllib.request.Request(W,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
try:
    print('  الويبهوك رجّع:', urllib.request.urlopen(rq,timeout=60).status)
except Exception as e:
    print('  ❌ فشل:', str(e)[:200])
"""], capture_output=True, text=True, timeout=120)
print((r2.stdout or r2.stderr).strip()[:400])

print("\n=== 5) مساحة ومتغيرات مهمة ===")
for k in ("GITHUB_TOKEN", "AUDIT_REPO"):
    print("  %s: %s" % (k, "موجود ✓" if os.environ.get(k) else "❌ مفقود"))
print("  الملفات في /data/results:", ", ".join(sorted(os.listdir("/data/results"))[-8:]) if os.path.isdir("/data/results") else "مفيش")

print("\nDONE-DIAG")
