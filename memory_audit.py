#!/usr/bin/env python3
"""حصر + نسخة احتياطية للذاكرة — قبل أي حذف (قراءة فقط، مفيش تعديل)."""
import base64, http.client, json, os, re, socket, urllib.request

SOCK = "/var/run/docker.sock"


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(200); sk.connect(s._p); s.sock = sk


def dk(m, p, b=None):
    c = U(SOCK); c.request(m, p, body=json.dumps(b).encode() if b is not None else None,
                           headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); raw = r.read(); c.close()
    try: return json.loads(raw.decode("utf-8", "ignore"))
    except Exception: return raw.decode("utf-8", "ignore")


def exec_in(cid, cmd):
    ex = dk("POST", "/containers/%s/exec" % cid,
            {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": False})
    eid = (ex or {}).get("Id")
    if not eid: return "(فشل)"
    c = U(SOCK)
    c.request("POST", "/exec/%s/start" % eid, body=json.dumps({"Detach": False, "Tty": False}).encode(),
              headers={"Content-Type": "application/json"})
    raw = c.getresponse().read(); c.close()
    out, i = [], 0
    while i + 8 <= len(raw):
        n = int.from_bytes(raw[i + 4:i + 8], "big")
        if n > len(raw) - i - 8: break
        out.append(raw[i + 8:i + 8 + n].decode("utf-8", "ignore")); i += 8 + n
    return ("".join(out) if out else raw.decode("utf-8", "ignore")).strip()


CS = dk("GET", "/containers/json")
name = lambda c: " ".join(c.get("Names") or [])
pg = [c for c in CS if "titan" in name(c) and "postgres" in name(c)][0]
env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m: env[m.group(1)] = m.group(2).strip()
P, UU, DB = env.get("PASSWORD", ""), env.get("USER", ""), env.get("DB", "")


def psql(sql, t='-tAc'):
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s %s \"%s\""
                              % (P, UU, DB, t, sql)])


print("█" * 78)
print("█  حصر ذاكرة تيتان (قراءة فقط — مفيش حذف)")
print("█" * 78)

print("\n━━━ ① النسخة الاحتياطية ━━━")
bk = exec_in(pg["Id"], ["sh", "-c",
                        "mkdir -p /tmp/bk && PGPASSWORD='%s' pg_dump -U %s -d %s "
                        "--data-only --table=user_context --table=memory_items --table=memory_messages "
                        "> /tmp/bk/memory_backup.sql 2>/dev/null; ls -la /tmp/bk/memory_backup.sql; "
                        "wc -l /tmp/bk/memory_backup.sql" % (P, UU, DB)])
print(bk[:400])

tok = os.environ.get("GITHUB_TOKEN", "")
if tok:
    raw = exec_in(pg["Id"], ["sh", "-c", "base64 -w0 /tmp/bk/memory_backup.sql"])
    b64 = "".join(raw.split())
    api = "https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/titan_memory_backup.sql"
    hdr = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "fawkes"}
    sha = None
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60)); sha = d.get("sha")
    except Exception: pass
    body = {"message": "backup: titan memory before cleaning", "content": b64}
    if sha: body["sha"] = sha
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(api, data=json.dumps(body).encode(), headers=hdr, method="PUT"), timeout=180))
        print("  ✅ النسخة الاحتياطية على GitHub:", r.get("content", {}).get("path"), "(%.1f KB)" % (len(b64) * 0.75 / 1024))
    except Exception as e:
        print("  ⚠️ رفع النسخة:", str(e)[:120])
else:
    print("  ⚠️ مفيش توكن GitHub — النسخة محلية بس")

print("\n━━━ ② كل صفوف user_context (اللي تيتان بيقرا منه) ━━━")
n = psql("SELECT count(*) FROM user_context").strip()
print("  العدد الكلي:", n)
rows = psql("SELECT owner_id || ' ┃ ' || key || ' ┃ ' || left(replace(value, E'\\n', ' '), 160) FROM user_context ORDER BY key")
for line in rows.splitlines()[:60]:
    if line.strip(): print("   ", line)

print("\n━━━ ③ عناصر الذاكرة (آخر 25) ━━━")
tot = psql("SELECT count(*) FROM memory_items").strip()
withvec = psql("SELECT count(embedding_vec) FROM memory_items").strip()
print("  الكلي:", tot, "· بتمثيل:", withvec)
rows2 = psql("SELECT left(replace(content, E'\\n', ' '), 150) FROM memory_items ORDER BY created_at DESC LIMIT 25")
for line in rows2.splitlines():
    if line.strip(): print("    •", line[:150])

print("\n━━━ ④ مفتاح «brother» وأخواته (الحقايق اللي اتعلّمها لوحده) ━━━")
for line in psql("SELECT key || ' ┃ ' || left(value, 300) FROM user_context WHERE key IN ('brother','sister','father','mother','wife','son','daughter','name','job','city','family','preferences','persona','learned')").splitlines():
    if line.strip(): print("   ", line[:320])

print("\n━━━ ⑤ علامات المعلومات الوهمية (اختبار) ━━━")
for pat in ["فاطمة", "مصطفى", "طنطا", "زحل", "تيتان أكبر", "خالتي", "أخويا"]:
    c = psql("SELECT count(*) FROM memory_items WHERE content ILIKE '%%%s%%'" % pat).strip()
    c2 = psql("SELECT count(*) FROM user_context WHERE value ILIKE '%%%s%%'" % pat).strip()
    print("   %-12s memory_items=%-5s user_context=%s" % (pat, c, c2))

print("\nDONE-AUDIT")
