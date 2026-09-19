#!/usr/bin/env python3
"""التحقق من خدمة التمثيل الجديدة (bge-m3) عن طريق Docker socket."""
import http.client, json, socket
SOCK="/var/run/docker.sock"
class U(http.client.HTTPConnection):
    def __init__(s,p): super().__init__("localhost"); s._p=p
    def connect(s):
        sk=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(300); sk.connect(s._p); s.sock=sk
def dk(m,p,b=None):
    c=U(SOCK); data=json.dumps(b).encode() if b is not None else None
    c.request(m,p,body=data,headers={"Content-Type":"application/json"} if b else {})
    r=c.getresponse(); raw=r.read(); c.close()
    try: return json.loads(raw.decode("utf-8","ignore"))
    except Exception: return raw.decode("utf-8","ignore")
def exec_in(cid,cmd):
    ex=dk("POST",f"/containers/{cid}/exec",{"Cmd":cmd,"AttachStdout":True,"AttachStderr":True,"Tty":True})
    eid=(ex or {}).get("Id")
    if not eid: return "(فشل)"
    c=U(SOCK); c.request("POST",f"/exec/{eid}/start",body=json.dumps({"Detach":False,"Tty":True}).encode(),headers={"Content-Type":"application/json"})
    raw=c.getresponse().read(); c.close(); return raw.decode("utf-8","ignore").strip()

cs=dk("GET","/containers/json")
svc=[c for c in (cs or []) if "embedsrv" in " ".join(c.get("Names") or [])]
if not svc:
    print("❌ حاوية embedsrv مش موجودة")
    print("الحاويات:", [ (c.get('Names') or [''])[0] for c in (cs or []) if 'grow' in ' '.join(c.get('Names') or []) ])
else:
    c=svc[0]
    print("الحاوية:", (c.get("Names") or [""])[0].lstrip("/"), "·", c.get("Status"))
    code = r'''
import json, urllib.request, time
def post(path, body):
    rq = urllib.request.Request("http://127.0.0.1:8080"+path, data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"})
    t0=time.time(); r=json.load(urllib.request.urlopen(rq, timeout=180)); return r, time.time()-t0
try:
    r, el = post("/v1/embeddings", {"input": "الطلب اتأخر ومحتاج حل"})
    v = r["data"][0]["embedding"]
    print("  ✅ الخدمة شغالة · الأبعاد:", len(v), "· الزمن:", round(el,2), "ث")
    import math
    def emb(t): return post("/v1/embeddings", {"input": t})[0]["data"][0]["embedding"]
    def cos(a,b):
        d=sum(x*y for x,y in zip(a,b)); na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(y*y for y in b)); return d/(na*nb)
    pairs=[("نفس المعنى","الطلب اتأخر وأنا محتاج حل بسرعة","أوردري متأخر ومحتاج مساعدة سريعة"),
           ("مختلف","الطلب اتأخر وأنا محتاج حل بسرعة","الطقس النهاردة جميل في ينبع")]
    for lbl,a,b in pairs:
        print(f"  {lbl:12} {cos(emb(a),emb(b)):.3f}")
except Exception as e:
    print("  ❌ فشل:", str(e)[:300])
'''
    import base64
    b64 = base64.b64encode(code.encode()).decode()
    exec_in(c["Id"], ["sh","-c",f"echo {b64} | base64 -d > /tmp/t.py"])
    print(exec_in(c["Id"], ["python3","/tmp/t.py"]) or "(مفيش مخرجات — لسه بيحمّل؟)")
