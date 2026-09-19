#!/usr/bin/env python3
"""نلاقي العنوان اللي تقدر حاويات تيتان توصل بيه لخدمة التمثيل."""
import json, socket, urllib.request, http.client, subprocess, math

print("=== 1) عنوان الشبكة من جوه الحاوية ===")
try:
    print("  route:", subprocess.run(["sh","-c","ip route 2>/dev/null | head -5 || cat /proc/net/route | head -3"],
                                    capture_output=True, text=True).stdout.strip())
except Exception as e:
    print("  ", e)

print("\n=== 2) تجربة العناوين المرشحة لمنفذ 8095 ===")
cands = []
try:
    out = subprocess.run(["sh","-c","ip route 2>/dev/null | awk '/default/ {print $3}'"], capture_output=True, text=True).stdout.split()
    cands += [c.strip() for c in out if c.strip()]
except Exception: pass
cands += ["172.17.0.1", "172.18.0.1", "172.19.0.1", "host.docker.internal"]

BODY = json.dumps({"input": "اختبار"}).encode()
def test(host, port=8095):
    try:
        rq = urllib.request.Request(f"http://{host}:{port}/v1/embeddings", data=BODY,
                                    headers={"Content-Type": "application/json"})
        r = json.load(urllib.request.urlopen(rq, timeout=20))
        return "✅ شغال · الأبعاد " + str(len(r["data"][0]["embedding"]))
    except Exception as e:
        return "❌ " + str(e)[:60]

for c in dict.fromkeys(cands):
    print(f"  {c:24} {test(c)}")

print("\n=== 3) الاختبار النهائي: جودة العربي من عنوان الشبكة ===")
import math
for host in dict.fromkeys(cands):
    try:
        def emb(t):
            rq = urllib.request.Request(f"http://{host}:8095/v1/embeddings", data=json.dumps({"input": t}).encode(),
                                        headers={"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(rq, timeout=60))["data"][0]["embedding"]
        def cos(a,b):
            return sum(x*y for x,y in zip(a,b))/(math.sqrt(sum(x*x for x in a))*math.sqrt(sum(y*y for y in b)))
        s = cos(emb("الطلب اتأخر ومحتاج حل"), emb("أوردري متأخر ومحتاج مساعدة"))
        d = cos(emb("الطلب اتأخر ومحتاج حل"), emb("الطقس جميل في ينبع"))
        print(f"  {host}: نفس المعنى {s:.3f} · مختلف {d:.3f} · الفرق {s-d:.3f}")
        print(f"  ➜ العنوان الصالح لتيتان: http://{host}:8095/v1")
        break
    except Exception as e:
        continue
