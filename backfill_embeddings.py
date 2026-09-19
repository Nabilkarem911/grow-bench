#!/usr/bin/env python3
"""backfill_embeddings.py — إعادة توليد تمثيل عناصر الذاكرة القديمة في تيتان.

بيشتغل من حاوية الفحص (جرو) عن طريق Docker socket:
  ١) يقرا بيانات اتصال Postgres من حاوية تيتان (بما فيها كلمة السر)
  ٢) ينفّذ سكربت جوّه حاوية التمثيل نفسها (عندها fastembed + النموذج)
  ٣) السكربت بيثبّت psycopg2، بيقرا العناصر اللي embedding_vec بتاعها فاضي،
     بيولّد تمثيل جديد بالعربي، وبيحدّث الصفوف.
آمن: بيملأ عمود فاضي بس — مفيش حذف ولا تعديل على بيانات موجودة.
"""
import base64, http.client, json, os, socket, urllib.request

SOCK = "/var/run/docker.sock"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = "Nabilkarem911/grow-bench"
OUT = []

def say(*a):
    line = " ".join(str(x) for x in a); print(line, flush=True); OUT.append(line)

class UnixHTTP(http.client.HTTPConnection):
    def __init__(s, p):
        super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(900); sk.connect(s._p); s.sock = sk

def dk(method, path, body=None):
    c = UnixHTTP(SOCK)
    data = json.dumps(body).encode() if body is not None else None
    c.request(method, path, body=data, headers={"Content-Type": "application/json"} if body else {})
    r = c.getresponse(); raw = r.read(); c.close()
    try: return r.status, json.loads(raw.decode("utf-8", "ignore"))
    except Exception: return r.status, raw.decode("utf-8", "ignore")

def exec_in(cid, cmd, tty=False):
    _, ex = dk("POST", f"/containers/{cid}/exec", {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": tty})
    eid = (ex or {}).get("Id")
    if not eid: return "(فشل exec)"
    c = UnixHTTP(SOCK)
    c.request("POST", f"/exec/{eid}/start", body=json.dumps({"Detach": False, "Tty": tty}).encode(),
              headers={"Content-Type": "application/json"})
    raw = c.getresponse().read(); c.close()
    if tty: return raw.decode("utf-8", "ignore").strip()
    out, i = [], 0
    while i + 8 <= len(raw):
        n = int.from_bytes(raw[i+4:i+8], "big"); out.append(raw[i+8:i+8+n].decode("utf-8", "ignore")); i += 8 + n
    return ("".join(out) if out else raw.decode("utf-8", "ignore")).strip()

WORKER = r'''
import json, subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "psycopg2-binary"], check=False)
import psycopg2
from fastembed import TextEmbedding

cfg = json.loads(open("/tmp/pgcfg.json").read())
m = TextEmbedding()
conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], dbname=cfg["db"], user=cfg["user"], password=cfg["pw"])
cur = conn.cursor()
cur.execute("SELECT id, content FROM memory_items WHERE embedding_vec IS NULL AND content IS NOT NULL LIMIT 500")
rows = cur.fetchall()
print("عناصر محتاجة تمثيل:", len(rows))
done = 0
for i in range(0, len(rows), 32):
    batch = rows[i:i+32]
    vecs = list(m.embed([r[1][:2000] for r in batch]))
    for (rid, _), v in zip(batch, vecs):
        arr = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
        cur.execute("UPDATE memory_items SET embedding_vec = %s::vector WHERE id = %s", (arr, rid))
        done += 1
    conn.commit()
    print(f"  اتعمل {done}/{len(rows)}")
cur.execute("SELECT COUNT(*), COUNT(embedding_vec) FROM memory_items")
tot, withv = cur.fetchone()
print(f"النتيجة: {withv} من {tot} عندهم متجه")
cur.close(); conn.close()
'''

def main():
    say("بدء الـbackfill...")
    _, cs = dk("GET", "/containers/json")
    titans = [c for c in (cs or []) if "titan" in " ".join(c.get("Names") or [])]
    emb = [c for c in titans if "embed" in " ".join(c.get("Names") or [])]
    pg = [c for c in titans if "postgres" in " ".join(c.get("Names") or [])]
    if not emb or not pg:
        say("❌ حاوية ناقصة"); return
    emb, pg = emb[0], pg[0]
    _, info = dk("GET", f"/containers/{pg['Id']}/json")
    env = {}
    for kv in (info.get("Config", {}).get("Env") or []):
        if "=" in kv:
            k, v = kv.split("=", 1); env[k] = v
    cfg = {"host": pg.get("Name", "").lstrip("/") or "titan-postgres",
           "port": 5432, "db": env.get("POSTGRES_DB", "titan"),
           "user": env.get("POSTGRES_USER", "postgres"), "pw": env.get("POSTGRES_PASSWORD", "")}
    # نحتاج اسم الشبكة/المضيف الصح — نستخدم اسم الحاوية
    names = " ".join(pg.get("Names") or []).lstrip("/")
    cfg["host"] = names
    say("قاعدة البيانات:", cfg["host"], "· المستخدم:", cfg["user"])
    # نكتب الإعدادات جوّه حاوية التمثيل
    b64 = base64.b64encode(json.dumps(cfg).encode()).decode()
    exec_in(emb["Id"], ["sh", "-c", f"echo {b64} | base64 -d > /tmp/pgcfg.json"])
    b64w = base64.b64encode(WORKER.encode()).decode()
    exec_in(emb["Id"], ["sh", "-c", f"echo {b64w} | base64 -d > /tmp/worker.py"])
    say("")
    say(exec_in(emb["Id"], ["python3", "/tmp/worker.py"]))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback; say("🚨", repr(e)[:300]); say(traceback.format_exc()[-800:])
