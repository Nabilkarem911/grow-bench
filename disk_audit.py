#!/usr/bin/env python3
"""فحص المساحة على السيرفر: مين واكل القرص بالظبط."""
import http.client, json, socket, subprocess


SOCK = "/var/run/docker.sock"


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p

    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(300); sk.connect(s._p); s.sock = sk


def dk(m, p, b=None):
    c = U(SOCK)
    c.request(m, p, body=json.dumps(b).encode() if b is not None else None,
              headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); raw = r.read(); c.close()
    try:
        return json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return raw.decode("utf-8", "ignore")


def sh(cmd):
    try:
        r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, timeout=240)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return "(فشل: %s)" % str(e)[:60]


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024
    return "%.1f PB" % n


print("=== 1) القرص ===")
print(sh("df -h / /data 2>/dev/null | head -8"))

print("\n=== 2) اللي في المجلد المشترك /data (أكبر 20) ===")
print(sh("du -sh /data/* 2>/dev/null | sort -h | tail -20"))

print("\n=== 3) الموديلات اللي نزّلناها ===")
print(sh("du -sh /data/moe 2>/dev/null; ls -lhS /data/moe/ 2>/dev/null | head -25"))

print("\n=== 4) llama.cpp ===")
print(sh("du -sh /data/llama 2>/dev/null; ls /data/llama 2>/dev/null | head"))

print("\n=== 5) مساحة Docker الحقيقية ===")
d = dk("GET", "/system/df")
if isinstance(d, dict):
    print("  طبقات الصور: %s" % human(d.get("LayersSize", 0)))
    print("  حاويات (كتابة): %s" % human(sum((c.get("SizeRw", 0) or 0) for c in d.get("Containers", []))))
    print("  فوليومات: %s" % human(sum(((v.get("UsageData") or {}).get("Size", 0) or 0) for v in d.get("Volumes", []))))
    bc = d.get("BuildCache") or []
    print("  كاش البناء: %s  (%d عنصر)" % (human(sum((x.get("Size", 0) or 0) for x in bc)), len(bc)))
    print("\n  أكبر 12 صورة:")
    for im in sorted(d.get("Images") or [], key=lambda x: -(x.get("Size", 0) or 0))[:12]:
        tags = im.get("RepoTags") or ["(بلا وسم)"]
        print("    %9s  %s" % (human(im.get("Size", 0)), str(tags[0])[:58]))
    print("\n  أكبر 6 فوليومات:")
    for v in sorted(d.get("Volumes") or [], key=lambda x: -(((x.get("UsageData") or {}).get("Size", 0)) or 0))[:6]:
        print("    %9s  %s" % (human((v.get("UsageData") or {}).get("Size", 0)), str(v.get("Name"))[:58]))
else:
    print("  ⚠️", str(d)[:150])

print("\n=== 6) حاويات بأكبر مساحة كتابة ===")
cs = dk("GET", "/containers/json?all=1")
if isinstance(cs, list):
    for c in sorted(cs, key=lambda x: -(x.get("SizeRw", 0) or 0))[:10]:
        print("    %9s  %s" % (human(c.get("SizeRw", 0)), (c.get("Names") or [""])[0].lstrip("/")[:50]))

print("\n=== 7) ملفات كبيرة (>200 ميجا) في /data ===")
print(sh("find /data -type f -size +200M 2>/dev/null | head -20 | while read f; do ls -lh \"$f\"; done"))

print("\nDONE-DISK-AUDIT")
