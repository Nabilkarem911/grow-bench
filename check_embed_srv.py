#!/usr/bin/env python3
"""الاختبار النهائي: إعادة تمثيل ذاكرة تيتان بخدمة bge-m3 + بحث عربي حقيقي."""
import http.client, json, socket, urllib.request, math, re


def embedding_text(content, max_len=900):
    """نفس قاعدة embeddingText في تيتان بالظبط (لازم تتطابق)."""
    flat = " ".join((content or "").split())
    if not flat: return ""
    parts = []
    m = re.search(r"Prompt:\s*(.*?)(?:\s*Answer:|$)", flat, re.I)
    a = re.search(r"Answer:\s*(.*)$", flat, re.I)
    if m and m.group(1).strip(): parts.append(m.group(1).strip())
    if a and a.group(1).strip(): parts.append(a.group(1).strip()[:300])
    return ((" | ".join(parts)) if parts else flat)[:max_len]

SOCK = "/var/run/docker.sock"
class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(600); sk.connect(s._p); s.sock = sk

def dk(m, p, b=None):
    c = U(SOCK)
    c.request(m, p, body=json.dumps(b).encode() if b is not None else None,
              headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); raw = r.read(); c.close()
    try: return json.loads(raw.decode("utf-8", "ignore"))
    except Exception: return raw.decode("utf-8", "ignore")

def exec_in(cid, cmd, wd="/"):
    """بدون PTY — مع فك ترويسات التدفق (8 بايت لكل إطار) — يتجنب تعليق Tty."""
    ex = dk("POST", f"/containers/{cid}/exec",
            {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": False, "WorkingDir": wd})
    eid = (ex or {}).get("Id")
    if not eid: return "(فشل exec)"
    c = U(SOCK)
    c.request("POST", f"/exec/{eid}/start",
              body=json.dumps({"Detach": False, "Tty": False}).encode(),
              headers={"Content-Type": "application/json"})
    raw = c.getresponse().read(); c.close()
    out, i = [], 0
    while i + 8 <= len(raw):
        try: n = int.from_bytes(raw[i+4:i+8], "big")
        except Exception: break
        if n > len(raw) - i - 8: break
        out.append(raw[i+8:i+8+n].decode("utf-8", "ignore")); i += 8 + n
    return ("".join(out) if out else raw.decode("utf-8", "ignore")).strip()

cs = dk("GET", "/containers/json")
def find(sub):
    for c in (cs or []):
        if sub in " ".join(c.get("Names") or []): return c
    return None

pg = find("titan-titan-wqx9l7-postgres")
if not pg:
    print("❌ مفيش حاوية postgres لتيتان"); print([ (c.get('Names') or [''])[0] for c in (cs or []) if 'titan' in ' '.join(c.get('Names') or []) ]); raise SystemExit

envtxt = exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"])
env = {}
for line in envtxt.splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m: env[m.group(1)] = m.group(2).strip()
print("قاعدة البيانات:", env.get("DB"), "· المستخدم:", env.get("USER"))

def psql(sql):
    q = f"export PGPASSWORD='{env.get('PASSWORD','')}'; psql -U {env.get('USER')} -d {env.get('DB')} -tAc \"{sql}\""
    return exec_in(pg["Id"], ["sh", "-c", q])

print("\n=== 1) أبعاد العمود بعد الترحيل ===")
print("  ", psql("SELECT format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='memory_items'::regclass AND attname='embedding_vec'"))
print("  الترحيلات المطبقة:", psql("SELECT string_agg(name,',') FROM (SELECT table_name AS name FROM information_schema.tables WHERE table_name ILIKE '%migration%') t").strip()[:120])

print("\n=== 2) إعادة توليد التمثيل (bge-m3 · 1024) ===")
raw = psql("SELECT coalesce(json_agg(json_build_object('id', id::text, 'content', left(coalesce(content,''),600))),'[]'::json) FROM memory_items")
try:
    recs = [(r["id"], r["content"]) for r in json.loads(raw.strip().splitlines()[-1])]
except Exception as e:
    print("  ⚠️ فشل قراءة العناصر:", str(e)[:80]); recs = []
print(f"  عدد العناصر: {len(recs)}")
sqls, ok, fail = [], 0, 0
for i, (mid, content) in enumerate(recs[:200]):
    text = content.replace("\\", " ").replace("'", " ") or " "
    try:
        rq = urllib.request.Request("https://embed.orcanox.xyz/v1/embeddings",
                                    data=json.dumps({"input": embedding_text(text)}).encode("utf-8"),
                                    headers={"Content-Type": "application/json"})
        vec = json.load(urllib.request.urlopen(rq, timeout=60))["data"][0]["embedding"]
        lit = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
        sqls.append("UPDATE memory_items SET embedding_vec='%s'::vector WHERE id::text='%s';" % (lit, str(mid).replace("'", "''")))
        ok += 1
    except Exception as e:
        fail += 1
    if (i+1) % 40 == 0: print(f"    ... {i+1}")
print(f"  ✅ جاهز: {ok} · فشل: {fail}")

if sqls:
    import tarfile, io
    cp = find("titan-titan-wqx9l7-postgres")
    # نرفع ملف SQL للحاوية عبر Docker archive API (مفيش حدود طول هنا)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        data = "\n".join(sqls).encode("utf-8")
        ti = tarfile.TarInfo(name="bf.sql"); ti.size = len(data); ti.mode = 0o644
        tf.addfile(ti, io.BytesIO(data))
    buf.seek(0)
    c = U(SOCK)
    c.request("PUT", f"/containers/{cp['Id']}/archive?path=/tmp", body=buf.read(),
              headers={"Content-Type": "application/x-tar"})
    r = c.getresponse(); print("  رفع الملف:", r.status, r.read()[:80]); c.close()
    out = exec_in(cp["Id"], ["sh", "-c",
        f"export PGPASSWORD='{env.get('PASSWORD','')}'; psql -U {env.get('USER')} -d {env.get('DB')} -q -f /tmp/bf.sql 2>&1 | tail -3; "
        f"psql -U {env.get('USER')} -d {env.get('DB')} -tAc \"SELECT count(*) FROM memory_items WHERE embedding_vec IS NOT NULL\""])
    print("  نتيجة التحديث:", out)

print("\n=== 3) البحث الدلالي الحقيقي في ذاكرة تيتان ===")
for q in ["تسويق المنتجات", "إيه اسمي", "قواعد الأمان"]:
    rq = urllib.request.Request("https://embed.orcanox.xyz/v1/embeddings",
                                data=json.dumps({"input": q}).encode("utf-8"),
                                headers={"Content-Type": "application/json"})
    qv = json.load(urllib.request.urlopen(rq, timeout=60))["data"][0]["embedding"]
    lit = "[" + ",".join(f"{x:.6f}" for x in qv) + "]"
    res = psql(f"SELECT round((1-(embedding_vec <=> '{lit}'::vector))::numeric,3)||' | '||coalesce(left(content,70),'') "
               f"FROM memory_items WHERE embedding_vec IS NOT NULL ORDER BY embedding_vec <=> '{lit}'::vector LIMIT 3")
    print(f"\n  🔎 «{q}»")
    for line in res.splitlines():
        if line.strip(): print("     ", line.strip())
