#!/bin/sh
LOG=/data/results/backup.log
mkdir -p /data/results
exec > "$LOG" 2>&1
echo "════════ نسخة احتياطية لقاعدة تيتان ════════"
python3 - <<'PY'
import http.client, json, re, socket, subprocess
SOCK="/var/run/docker.sock"
class U(http.client.HTTPConnection):
    def __init__(s,p): super().__init__("localhost"); s._p=p
    def connect(s):
        sk=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(600); sk.connect(s._p); s.sock=sk
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
pg=[c for c in (cs or []) if "titan-titan-wqx9l7-postgres" in " ".join(c.get("Names") or [])][0]
env={}
for line in exec_in(pg["Id"],["sh","-c","env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m=re.match(r"export POSTGRES_(\w+)=(.*)",line.strip())
    if m: env[m.group(1)]=m.group(2).strip()
print("بنعمل pg_dump...")
r=exec_in(pg["Id"],["sh","-c","export PGPASSWORD='%s'; pg_dump -U %s -d %s --no-owner > /tmp/titan_backup.sql && ls -lh /tmp/titan_backup.sql"%(env.get("PASSWORD",""),env.get("USER"),env.get("DB"))])
print(r)
print("عدد الجداول في النسخة:", exec_in(pg["Id"],["sh","-c","grep -c 'CREATE TABLE' /tmp/titan_backup.sql"]).strip())
print("\nDONE-BACKUP")
PY
python3 - <<'UPLOAD'
import base64, json, os, urllib.request
tok = os.environ.get("GITHUB_TOKEN", "")
if not tok: raise SystemExit
data = open("/data/results/backup.log", "rb").read().decode("utf-8", "ignore")
api = "https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/backup.log"
hdr = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "fawkes"}
sha = None
try:
    d = json.load(urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60)); sha = d.get("sha")
except Exception: pass
body = {"message": "titan db backup", "content": base64.b64encode(data.encode()).decode()}
if sha: body["sha"] = sha
print("✅", json.load(urllib.request.urlopen(urllib.request.Request(api, data=json.dumps(body).encode(), headers=hdr, method="PUT"), timeout=90)).get("content", {}).get("path"))
UPLOAD
