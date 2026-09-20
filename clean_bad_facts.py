#!/usr/bin/env python3
"""يمسح الحقايق السيئة اللي استخرجها الموديل الصغير (تنظيف ذاكرتنا)."""
import http.client, json, re, socket

SOCK="/var/run/docker.sock"
class U(http.client.HTTPConnection):
    def __init__(s,p): super().__init__("localhost"); s._p=p
    def connect(s):
        sk=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(300); sk.connect(s._p); s.sock=sk
def dk(m,p,b=None):
    c=U(SOCK); c.request(m,p,body=json.dumps(b).encode() if b is not None else None,
        headers={"Content-Type":"application/json"} if b else {})
    r=c.getresponse(); raw=r.read(); c.close()
    try: return json.loads(raw.decode("utf-8","ignore"))
    except Exception: return raw.decode("utf-8","ignore")
def exec_in(cid,cmd,wd="/"):
    ex=dk("POST","/containers/%s/exec"%cid,{"Cmd":cmd,"AttachStdout":True,"AttachStderr":True,"Tty":False,"WorkingDir":wd})
    eid=(ex or {}).get("Id")
    if not eid: return "(فشل)"
    c=U(SOCK); c.request("POST","/exec/%s/start"%eid,body=json.dumps({"Detach":False,"Tty":False}).encode(),
        headers={"Content-Type":"application/json"})
    raw=c.getresponse().read(); c.close()
    out,i=[],0
    while i+8<=len(raw):
        n=int.from_bytes(raw[i+4:i+8],"big")
        if n>len(raw)-i-8: break
        out.append(raw[i+8:i+8+n].decode("utf-8","ignore")); i+=8+n
    return ("".join(out) if out else raw.decode("utf-8","ignore")).strip()

cs=dk("GET","/containers/json")
pg=[c for c in (cs or []) if "titan-titan-wqx9l7-postgres" in " ".join(c.get("Names") or [])]
if not pg: print("❌ مفيش postgres"); raise SystemExit
pg=pg[0]
env={}
for line in exec_in(pg["Id"],["sh","-c","env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m=re.match(r"export POSTGRES_(\w+)=(.*)",line.strip())
    if m: env[m.group(1)]=m.group(2).strip()
def psql(sql):
    return exec_in(pg["Id"],["sh","-c","export PGPASSWORD='%s'; psql -U %s -d %s -tAc \"%s\""%(env.get("PASSWORD",""),env.get("USER"),env.get("DB"),sql)])

print("=== قبل ===")
print("  إجمالي العناصر:", psql("SELECT count(*) FROM memory_items").strip())
print("  حقايق مستخرجة:", psql("SELECT count(*) FROM memory_items WHERE metadata->>'derived'='fact'").strip())
print("\n=== نماذج من الحقايق (للتأكيد إن دي بتاعتنا) ===")
print(psql("SELECT left(content,70) FROM memory_items WHERE metadata->>'derived'='fact' LIMIT 5"))
print("\n=== بنمسح ===")
print("  ", psql("DELETE FROM memory_items WHERE metadata->>'derived'='fact'").strip())
print("\n=== بعد ===")
print("  إجمالي العناصر:", psql("SELECT count(*) FROM memory_items").strip())
print("  حقايق فاضلة:", psql("SELECT count(*) FROM memory_items WHERE metadata->>'derived'='fact'").strip())
print("\n=== بنتأكد إن العناصر الأصلية والمركّزة لسه موجودة ===")
print(psql("SELECT coalesce(metadata->>'derived','turn')||' = '||count(*) FROM memory_items GROUP BY metadata->>'derived'"))
print("\nDONE-CLEAN-FACTS")
