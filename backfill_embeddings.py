#!/usr/bin/env python3
"""الاختبار النهائي: بحث دلالي حقيقي في ذاكرة تيتان."""
import base64, http.client, json, os, socket

SOCK = "/var/run/docker.sock"
OUT = []
def say(*a):
    line = " ".join(str(x) for x in a); print(line, flush=True); OUT.append(line)

class UnixHTTP(http.client.HTTPConnection):
    def __init__(s, p):
        super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(600); sk.connect(s._p); s.sock = sk

def dk(method, path, body=None):
    c = UnixHTTP(SOCK)
    data = json.dumps(body).encode() if body is not None else None
    c.request(method, path, body=data, headers={"Content-Type": "application/json"} if body else {})
    r = c.getresponse(); raw = r.read(); c.close()
    try: return r.status, json.loads(raw.decode("utf-8", "ignore"))
    except Exception: return r.status, raw.decode("utf-8", "ignore")

def exec_in(cid, cmd):
    _, ex = dk("POST", f"/containers/{cid}/exec", {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": True})
    eid = (ex or {}).get("Id")
    if not eid: return "(فشل)"
    c = UnixHTTP(SOCK)
    c.request("POST", f"/exec/{eid}/start", body=json.dumps({"Detach": False, "Tty": True}).encode(),
              headers={"Content-Type": "application/json"})
    raw = c.getresponse().read(); c.close()
    return raw.decode("utf-8", "ignore").strip()

WORKER = r'''
import json, subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "psycopg2-binary"], check=False)
import psycopg2
from fastembed import TextEmbedding
cfg = json.loads(open("/tmp/pgcfg.json").read())
m = TextEmbedding()
conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], dbname=cfg["db"], user=cfg["user"], password=cfg["pw"])
cur = conn.cursor()
cur.execute("SELECT COUNT(*), COUNT(embedding_vec) FROM memory_items")
say("المخزون:", cur.fetchone())

for q in ["الطلب اتأخر ومحتاج حل", "مشكلة في الفاتورة", "اجتماع أو مهمة"]:
    v = list(m.embed([q]))[0]
    arr = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
    cur.execute("""
        SELECT content, 1 - (embedding_vec <=> %s::vector) AS sim
        FROM memory_items WHERE embedding_vec IS NOT NULL
        ORDER BY embedding_vec <=> %s::vector LIMIT 3
    """, (arr, arr))
    print(f"\n🔎 الاستعلام: {q}")
    for c, s in cur.fetchall():
        print(f"   [{s:.3f}] {str(c)[:110].replace(chr(10),' ')}")
cur.close(); conn.close()
'''
WORKER = WORKER.replace('say("المخزون:", cur.fetchone())', 'print("المخزون:", cur.fetchone())')

def main():
    _, cs = dk("GET", "/containers/json")
    titans = [c for c in (cs or []) if "titan" in " ".join(c.get("Names") or [])]
    emb = [c for c in titans if "embed" in " ".join(c.get("Names") or [])][0]
    pg = [c for c in titans if "postgres" in " ".join(c.get("Names") or [])][0]
    _, info = dk("GET", f"/containers/{pg['Id']}/json")
    env = {}
    for kv in (info.get("Config", {}).get("Env") or []):
        if "=" in kv:
            k, v = kv.split("=", 1); env[k] = v
    cfg = {"host": " ".join(pg.get("Names") or []).lstrip("/"), "port": 5432,
           "db": env.get("POSTGRES_DB", "titan"), "user": env.get("POSTGRES_USER", "titan"),
           "pw": env.get("POSTGRES_PASSWORD", "")}
    b64 = base64.b64encode(json.dumps(cfg).encode()).decode()
    exec_in(emb["Id"], ["sh", "-c", f"echo {b64} | base64 -d > /tmp/pgcfg.json"])
    b64w = base64.b64encode(WORKER.encode()).decode()
    exec_in(emb["Id"], ["sh", "-c", f"echo {b64w} | base64 -d > /tmp/worker.py"])
    say(exec_in(emb["Id"], ["python3", "/tmp/worker.py"]))

try:
    main()
except Exception as e:
    say("🚨", repr(e)[:300])
