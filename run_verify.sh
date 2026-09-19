#!/bin/sh
LOG=/data/results/arabic_memory_verify.log
mkdir -p /data/results
exec > "$LOG" 2>&1
echo "════════ تشخيص خدمة التمثيل ════════"
python3 - <<'PY'
import http.client, json, socket, base64
SOCK="/var/run/docker.sock"
class U(http.client.HTTPConnection):
    def __init__(s,p): super().__init__("localhost"); s._p=p
    def connect(s):
        sk=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(120); sk.connect(s._p); s.sock=sk
def dk(m,p,b=None):
    c=U(SOCK); data=json.dumps(b).encode() if b is not None else None
    c.request(m,p,body=data,headers={"Content-Type":"application/json"} if b else {})
    r=c.getresponse(); raw=r.read(); c.close()
    try: return json.loads(raw.decode("utf-8","ignore"))
    except Exception: return raw.decode("utf-8","ignore")
def exec_in(cid,cmd):
    ex=dk("POST",f"/containers/{cid}/exec",{"Cmd":cmd,"AttachStdout":True,"AttachStderr":True,"Tty":True})
    eid=(ex or {}).get("Id")
    if not eid: return "(فشل exec)"
    c=U(SOCK); c.request("POST",f"/exec/{eid}/start",body=json.dumps({"Detach":False,"Tty":True}).encode(),headers={"Content-Type":"application/json"})
    raw=c.getresponse().read(); c.close(); return raw.decode("utf-8","ignore").strip()
cs=dk("GET","/containers/json")
svc=[c for c in (cs or []) if "embedsrv" in " ".join(c.get("Names") or [])]
if not svc: print("❌ مفيش حاوية embedsrv"); raise SystemExit
c=svc[0]
print("الحالة:", c.get("Status"))
info=dk("GET",f"/containers/{c['Id']}/json")
print("عدد مرات الإعادة:", info.get("RestartCount"), "· آخر خروج:", (info.get("State") or {}).get("ExitCode"))
print("")
print("--- ملفات الموديل ---")
print(exec_in(c["Id"], ["sh","-c","ls -la /data/moe/ 2>/dev/null | grep -i bge || echo 'مفيش موديل لسه'"]))
print("")
print("--- llama-server موجود؟ ---")
print(exec_in(c["Id"], ["sh","-c","ls -la /data/llama/llama-server 2>/dev/null || echo 'مش موجود!'"]))
print("")
print("--- العمليات ---")
print(exec_in(c["Id"], ["sh","-c","ps aux 2>/dev/null | head -12 || ps -ef | head -12"]))
PY
echo ""
echo "DONE-ARABIC-VERIFY"
python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok=os.environ.get("GITHUB_TOKEN","")
if not tok: raise SystemExit
data=open("/data/results/arabic_memory_verify.log","rb").read().decode("utf-8","ignore")
api="https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/arabic_memory_verify.log"
hdr={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"fawkes"}
sha=None
try:
    d=json.load(urllib.request.urlopen(urllib.request.Request(api,headers=hdr),timeout=60)); sha=d.get("sha")
except Exception: pass
body={"message":"embedsrv diag","content":base64.b64encode(data.encode()).decode()}
if sha: body["sha"]=sha
print("✅", json.load(urllib.request.urlopen(urllib.request.Request(api,data=json.dumps(body).encode(),headers=hdr,method="PUT"),timeout=90)).get("content",{}).get("path"))
UPLOAD
