#!/usr/bin/env python3
"""إنشاء شبكة مشتركة (embeds) + فحص الحالة."""
import http.client, json, socket

SOCK = "/var/run/docker.sock"
class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(120); sk.connect(s._p); s.sock = sk

def dk(m, p, b=None):
    c = U(SOCK)
    c.request(m, p, body=json.dumps(b).encode() if b is not None else None,
              headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); raw = r.read(); c.close()
    try: return json.loads(raw.decode("utf-8", "ignore"))
    except Exception: return raw.decode("utf-8", "ignore")

print("=== 1) الشبكات الحالية ===")
for n in dk("GET", "/networks"):
    nm = n.get("Name", "")
    if "grow" in nm or "titan" in nm or nm == "embeds":
        print(f"  {nm:42} {n.get('Driver')}")

print("\n=== 2) إنشاء شبكة embeds (لو مش موجودة) ===")
ex = [n for n in dk("GET", "/networks") if n.get("Name") == "embeds"]
if ex:
    print("  موجودة بالفعل:", ex[0].get("Id", "")[:12])
else:
    r = dk("POST", "/networks/create", {"Name": "embeds", "Driver": "bridge",
                                        "CheckDuplicate": True,
                                        "Labels": {"purpose": "shared embed service"}})
    print("  النتيجة:", r.get("Id", r)[:60] if isinstance(r, dict) else str(r)[:120])

print("\n=== 3) تأكيد ===")
for n in dk("GET", "/networks"):
    if n.get("Name") == "embeds":
        print("  ✅ embeds:", n.get("Id", "")[:12], "· حاويات:", len((n.get("Containers") or {})))
