#!/usr/bin/env python3
"""اختبار دورة الحفظ والاسترجاع كاملة + backfill للعناصر بدون تمثيل.

السبب اللي اكتشفناه:
1) عميل الذاكرة في تيتان بيرجّع null (EMBEDDING_BASE_URL مش مضبوط) → مفيش تمثيل.
2) مسار المحادثة **مش** بيدوّر في memory_items أصلاً — بيقرا من user_context.
   → أي حاجة تتكتب في الذاكرة الدلالية لوحدها = مفيش حد بيشوفها.
"""
import http.client, json, re, socket, time, urllib.request

SOCK = "/var/run/docker.sock"
W = "https://titan.orcanox.xyz/telegram/webhook"
CHAT = 495185511
EMBED = "https://embed.orcanox.xyz/v1/embeddings"


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
pg = [c for c in CS if "titan" in name(c) and "postgres" in name(c)]
if not pg:
    print("❌ مفيش postgres"); print("DONE-LEARN2"); raise SystemExit
pg = pg[0]

env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m: env[m.group(1)] = m.group(2).strip()


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -tAc \"%s\""
                              % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)])


def embed(text):
    rq = urllib.request.Request(EMBED, data=json.dumps({"input": text, "model": "bge-m3"}).encode("utf-8"),
                                headers={"Content-Type": "application/json"})
    j = json.load(urllib.request.urlopen(rq, timeout=60))
    return j["data"][0]["embedding"]


print("━━━ ① خدمة التمثيل شغالة؟ ━━━")
try:
    v = embed("اختبار")
    print("  ✅ بُعد التمثيل:", len(v))
except Exception as e:
    print("  ❌ فشل:", str(e)[:150]); print("DONE-LEARN2"); raise SystemExit

print("\n━━━ ② backfill للعناصر بدون تمثيل ━━━")
n_null = psql("SELECT count(*) FROM memory_items WHERE embedding_vec IS NULL").strip()
print("  عناصر بدون تمثيل:", n_null)
if n_null not in ("0", ""):
    rows = psql("SELECT external_id || '\\t' || replace(replace(content, E'\\n', ' '), E'\\t', ' ') "
                "FROM memory_items WHERE embedding_vec IS NULL LIMIT 60")
    lines = [r for r in rows.splitlines() if r.strip()]
    stmts = []
    ok = 0
    for ln in lines:
        parts = ln.split("\t", 1)
        if len(parts) != 2: continue
        ext_id, content = parts
        try:
            vec = embed(content[:900])
            lit = "[" + ",".join("%.6f" % x for x in vec) + "]"
            stmts.append("UPDATE memory_items SET embedding_vec = '%s'::vector WHERE external_id = '%s';"
                         % (lit, ext_id.replace("'", "''")))
            ok += 1
        except Exception as e:
            print("   ⚠️", ext_id[:20], str(e)[:60])
    print("  اتحسب تمثيل لـ:", ok, "عنصر")
    if stmts:
        # مهم: ملف مش وسيط شل (حد الوسائط بياكل الملفات الكبيرة)
        sql = "\n".join(stmts)
        n = exec_in(pg["Id"], ["sh", "-c", "cat > /tmp/bf.sql <<'SQLEOF'\n%s\nSQLEOF\nPGPASSWORD='%s' psql -U %s -d %s -q -f /tmp/bf.sql 2>&1 | tail -3"
                                % (sql, env.get("PASSWORD", ""), env.get("USER", ""), env.get("DB", ""))])
        print("  التنفيذ:", n[:200])
    n_null2 = psql("SELECT count(*) FROM memory_items WHERE embedding_vec IS NULL").strip()
    print("  بعد الـbackfill — بدون تمثيل:", n_null2)

print("\n━━━ ③ نحفظ معلومة جديدة (الدورة الكاملة) ━━━")
FACT = "أخويا اسمه مصطفى وبيشتغل مهندس في القاهرة وبيحب القهوة التركي"
body = {"update_id": 9890, "message": {"message_id": 9890,
        "from": {"id": CHAT, "is_bot": False, "first_name": "Nabil"},
        "chat": {"id": CHAT, "type": "private"}, "date": int(time.time()), "text": FACT}}
try:
    urllib.request.urlopen(urllib.request.Request(W, data=json.dumps(body).encode(),
                                                  headers={"Content-Type": "application/json"}), timeout=60)
    print("  ✅ اتبعتت:", FACT)
except Exception as e:
    print("  ❌", str(e)[:120])

t0 = time.time()
while time.time() - t0 < 200:
    r = psql("SELECT coalesce(max(status),'') FROM agent_runs WHERE created_at > now() - interval '5 minutes' AND prompt ILIKE '%مصطفى%'")
    if r.strip() in ("completed", "failed"):
        print("  ✅ الرد خلص:", r.strip()); break
    time.sleep(15)
time.sleep(30)

print("\n━━━ ④ هل المعلومة وصلت للمكان الصح؟ ━━━")
uc = psql("SELECT key || ' :: ' || left(value,200) FROM user_context WHERE value ILIKE '%مصطفى%' ORDER BY updated_at DESC LIMIT 3")
print("  user_context (اللي تيتان بيقرا منه):")
print("   ", " ".join(uc.split())[:400] if uc.strip() else "❌ مفيش")
invec = psql("SELECT count(*) FROM memory_items WHERE content ILIKE '%مصطفى%' AND embedding_vec IS NOT NULL")
print("  memory_items (مع تمثيل):", invec.strip())

print("\n━━━ ⑤ اختبار الاسترجاع: تيتان فاكر؟ ━━━")
body2 = {"update_id": 9891, "message": {"message_id": 9891,
         "from": {"id": CHAT, "is_bot": False, "first_name": "Nabil"},
         "chat": {"id": CHAT, "type": "private"}, "date": int(time.time()),
         "text": "أخويا اسمه إيه وبيشتغل إيه وبيرشب إيه؟"}}
try:
    urllib.request.urlopen(urllib.request.Request(W, data=json.dumps(body2).encode(),
                                                  headers={"Content-Type": "application/json"}), timeout=60)
    print("  ✅ السؤال اتبعت")
except Exception as e:
    print("  ❌", str(e)[:100])
time.sleep(120)
ans = " ".join(psql("SELECT left(content,500) FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1").split())
print("  الرد:", ans[:450])
print("\n  🎯 التقييم:", "✅ تيتان فاكر!" if ("مصطفى" in ans and ("قهو" in ans or "مهندس" in ans)) else "❌ لسه مش فاكر")

print("\nDONE-LEARN2")
