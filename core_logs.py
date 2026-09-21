#!/usr/bin/env python3
"""نقرا لوجات core فورًا — هل الرسايل بتفشل؟"""
import http.client, json, socket

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


def logs_of(cid, tail=70):
    raw = dk("GET", "/containers/%s/logs?stdout=1&stderr=1&tail=%d" % (cid, tail), raw=True)
    out, i = [], 0
    while i + 8 <= len(raw):
        n = int.from_bytes(raw[i + 4:i + 8], "big")
        if n > len(raw) - i - 8:
            break
        out.append(raw[i + 8:i + 8 + n].decode("utf-8", "ignore")); i += 8 + n
    return "".join(out) if out else raw.decode("utf-8", "ignore")


cs = dk("GET", "/containers/json")
core = [c for c in (cs or []) if "titan-titan-wqx9l7-core-1" in " ".join(c.get("Names") or [])]
if not core:
    print("❌ مفيش core")
    raise SystemExit
lg = logs_of(core[0]["Id"], 60)
print("=== آخر 60 سطر من core ===")
for line in lg.splitlines()[-60:]:
    print("  " + line[:260])

print("\n=== الأخطاء بس ===")
for line in lg.splitlines():
    if any(k in line.lower() for k in ("error", "fail", "exception", "invalid", "500", "400", "unhandled")):
        print("  ⚠️ " + line[:260])

print("\n=== أي سطر فيه chat أو telegram في آخر 10 دقايق ===")
for line in lg.splitlines():
    if any(k in line.lower() for k in ("chat", "telegram", "message")):
        print("  " + line[:240])
