#!/usr/bin/env python3
"""نقرا سجلّات حاوية التمثيل مباشرة من Docker API (بدون exec)."""
import http.client, json, socket

SOCK = "/var/run/docker.sock"

class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(120); sk.connect(s._p); s.sock = sk

def dk(m, p, b=None):
    c = U(SOCK); data = json.dumps(b).encode() if b is not None else None
    c.request(m, p, body=data, headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); raw = r.read(); c.close()
    return raw

cs = json.loads(dk("GET", "/containers/json?all=1").decode("utf-8", "ignore"))
svc = [c for c in cs if "embedsrv" in " ".join(c.get("Names") or [])]
if not svc:
    print("❌ مفيش حاوية embedsrv"); raise SystemExit
c = svc[0]
info = json.loads(dk("GET", f"/containers/{c['Id']}/json").decode("utf-8", "ignore"))
st = info.get("State") or {}
print("الحالة:", c.get("Status"), "· الإعادات:", info.get("RestartCount"), "· كود الخروج:", st.get("ExitCode"))
print("مسار العمل:", (info.get("Config") or {}).get("WorkingDir"))
print("الأمر:", str((info.get("Config") or {}).get("Cmd"))[:160])
print("\n=== سجلّات الحاوية (آخر 2000 حرف) ===")
raw = dk("GET", f"/containers/{c['Id']}/logs?stdout=1&stderr=1&tail=80")
# إزالة ترويسات التدفق
out, i = [], 0
while i + 8 <= len(raw):
    n = int.from_bytes(raw[i+4:i+8], "big"); out.append(raw[i+8:i+8+n].decode("utf-8", "ignore")); i += 8 + n
txt = "".join(out) if out else raw.decode("utf-8", "ignore")
print(txt[-2000:])
