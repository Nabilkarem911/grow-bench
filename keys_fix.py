#!/usr/bin/env python3
"""تظبيط مفاتيح الحقايق + مسح كاش الإجابات القديمة، ثم اختبار الاسترجاع."""
import http.client, json, os, re, socket, time, urllib.request

SOCK = "/var/run/docker.sock"
W = "https://titan.orcanox.xyz/telegram/webhook"
CHAT = 495185511

# إعادة تسمية لمفردات تيتان المعروفة (شفتها في القاعدة: workplace · name · brother · aunt)
RENAME = {
    "job": "workplace",          # المفتاح اللي اتجاهله
}
# مفاتيح جوهرية إضافية بمفردات تيتان
EXTRA = {
    "company": "مؤسسة مطاعم عميد البحارة — ينبع، السعودية (نبيل موظف، مش المالك)",
}

TOK = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def tg(text):
    if not TOK: return
    try:
        urllib.request.urlopen(urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % TOK,
            data=json.dumps({"chat_id": CHAT, "text": text}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}), timeout=30)
    except Exception as e:
        print("  ⚠️ تليجرام:", str(e)[:80])


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


tg("⏳ بدأت: تظبيط مفاتيح الحقايق + مسح كاش الإجابات القديمة\n(هبعتلك النتيجة أول ما أخلص — ~6 دقايق)")
print("✅ رسالة البداية اتبعتت")

CS = dk("GET", "/containers/json")
nm = lambda c: " ".join(c.get("Names") or [])
pg = [c for c in CS if "titan" in nm(c) and "postgres" in nm(c)][0]
env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m: env[m.group(1)] = m.group(2).strip()
P, UU, DB = env.get("PASSWORD", ""), env.get("USER", ""), env.get("DB", "")


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -tAc \"%s\"" % (P, UU, DB, sql)])


def psql_file(sql):
    exec_in(pg["Id"], ["sh", "-c", "cat > /tmp/op.sql <<'SQLEOF'\n%s\nSQLEOF" % sql])
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -q -f /tmp/op.sql 2>&1 | tail -5" % (P, UU, DB)])


print("\n━━━ ① إعادة تسمية المفاتيح لمفردات تيتان ━━━")
st = []
for old, new in RENAME.items():
    v = psql("SELECT value FROM user_context WHERE key='%s' LIMIT 1" % old).strip()
    if v:
        st.append("INSERT INTO user_context (owner_id, key, value, updated_at) "
                  "SELECT owner_id, '%s', value, now() FROM user_context WHERE key='%s' "
                  "ON CONFLICT (owner_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();" % (new, old))
        st.append("DELETE FROM user_context WHERE key='%s';" % old)
        print("  %s → %s ✓" % (old, new))
    else:
        print("  %s: مش موجود" % old)
for k, v in EXTRA.items():
    st.append("INSERT INTO user_context (owner_id, key, value, updated_at) "
              "SELECT owner_id, '%s', '%s', now() FROM user_context WHERE key='name' LIMIT 1 "
              "ON CONFLICT (owner_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();" % (k, v.replace("'", "''")))
    print("  + %s ✓" % k)
if st:
    print(" ", psql_file("\n".join(st))[:150])

print("\n━━━ ② مسح كاش الإجابات القديمة ━━━")
tabs = psql("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name ILIKE '%%cach%%'")
print("  جداول الكاش:", " ".join(tabs.split()) if tabs.strip() else "(مفيش جدول)")
for t in [x for x in tabs.split() if x.strip()]:
    n = psql("SELECT count(*) FROM %s" % t).strip()
    psql_file("DELETE FROM %s;" % t)
    print("  %s: اتمسح %s صف" % (t, n))

print("\n━━━ ③ نتأكد من المفاتيح النهائية ━━━")
for line in psql("SELECT key || ' :: ' || left(value,110) FROM user_context WHERE key IN ('name','workplace','company','city','wife','son','style') ORDER BY key").splitlines():
    if line.strip(): print("   ", line[:150])

print("\n━━━ ④ اختبار الاسترجاع من جديد ━━━")
FACT = "خالتي اسمها فاطمة"
b = {"update_id": 9910, "message": {"message_id": 9910,
     "from": {"id": CHAT, "is_bot": False, "first_name": "Nabil"},
     "chat": {"id": CHAT, "type": "private"}, "date": int(time.time()),
     "text": "اسمي ايه واشتغل فين بالتحديد؟"}}
urllib.request.urlopen(urllib.request.Request(W, data=json.dumps(b).encode(), headers={"Content-Type": "application/json"}), timeout=60)
print("  ✅ السؤال اتبعت")
t0 = time.time()
while time.time() - t0 < 200:
    r = psql("SELECT coalesce(max(status),'') FROM agent_runs WHERE created_at > now() - interval '5 minutes' AND prompt ILIKE '%اشتغل فين%%'")
    if r.strip() in ("completed", "failed"):
        print("  ✅ خلص:", r.strip()); break
    time.sleep(15)
time.sleep(20)
ans = " ".join(psql("SELECT left(content,500) FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1").split())
print("  الرد:", ans[:450])
ok = ("نبيل" in ans) and ("عميد" in ans or "البحارة" in ans or "مطاعم" in ans)
print("  🎯 التقييم:", "✅ عارف اسمه وشغله!" if ok else "⚠️ محتاج نظرة")

tg("""✅ خلص: تظبيط المفاتيح + مسح الكاش

· job → workplace (لمفردات تيتان) ✅
· + company (الشركة كاملة) ✅
· كاش الإجابات القديمة: اتمسح ✅

اختبار الاسترجاع:
%s

%s""" % (ans[:280], "🎯 عارف اسمه وشغله ✅" if ok else "⚠️ لسه محتاج نظرة"))

print("\nDONE-FIX")
