#!/usr/bin/env python3
"""تحقق: هل تيتان بيتعلّم؟ (التعلّم التلقائي في الذاكرة)"""
import http.client, json, os, re, socket, time, urllib.request

SOCK = "/var/run/docker.sock"
W = "https://titan.orcanox.xyz/telegram/webhook"
CHAT = 495185511


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
    print("❌ مفيش postgres"); print("DONE-LEARN"); raise SystemExit
pg = pg[0]

env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m: env[m.group(1)] = m.group(2).strip()


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -tAc \"%s\""
                              % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)])


print("━━━ ① إجمالي الذاكرة قبل (للمقارنة) ━━━")
before = psql("SELECT count(*) FROM memory_items")
print("  عناصر قبل:", before.strip())

print("\n━━━ ② جِدول الذاكرة (نتأكد من الأعمدة) ━━━")
print(exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -c \"\\d memory_items\""
                          % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB", ""))])[:900])

print("\n━━━ ③ نرسل معلومة دائمة جديدة ━━━")
FACT = "خالتي اسمها فاطمة وساكنة في طنطا وبتحب الشاي بالنعناع"
body = {"update_id": 9870, "message": {"message_id": 9870,
        "from": {"id": CHAT, "is_bot": False, "first_name": "Nabil"},
        "chat": {"id": CHAT, "type": "private"}, "date": int(time.time()), "text": FACT}}
try:
    st = urllib.request.urlopen(urllib.request.Request(W, data=json.dumps(body).encode(),
                                                       headers={"Content-Type": "application/json"}), timeout=60).status
    print("  الويبهوك:", st, "· الرسالة:", FACT)
except Exception as e:
    print("  ❌", str(e)[:120])

print("\n  بنستنى الرد + التعلّم (fire-and-forget)...")
t0 = time.time(); done = False
while time.time() - t0 < 200:
    r = psql("SELECT coalesce(max(status),'') FROM agent_runs WHERE created_at > now() - interval '5 minutes' AND prompt ILIKE '%فاطمة%'")
    if r.strip() in ("completed", "failed"):
        done = True; print("  ✅ الرد خلص:", r.strip()); break
    time.sleep(15)
if not done: print("  ⏳ لسه")

time.sleep(25)  # مهلة التعلّم

print("\n━━━ ④ هل اتحفظت في الذاكرة؟ ━━━")
after = psql("SELECT count(*) FROM memory_items").strip()
print("  عناصر بعد:", after, " (قبل:", before.strip(), ")")
hit = psql("SELECT count(*) FROM memory_items WHERE content ILIKE '%فاطمة%' OR content ILIKE '%طنطا%'")
print("  عناصر فيها المعلومة الجديدة:", hit.strip())
print("  المحتوى المحفوظ:")
print("   ", " ".join(psql("SELECT left(content,300) FROM memory_items WHERE content ILIKE '%فاطمة%' ORDER BY created_at DESC LIMIT 2").split())[:400])
print("\n  رسالة الرد:")
print("   ", " ".join(psql("SELECT left(content,300) FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1").split())[:350])

print("\n━━━ ⑤ اختبار الاسترجاع: تيتان فاكر؟ ━━━")
body2 = {"update_id": 9871, "message": {"message_id": 9871,
         "from": {"id": CHAT, "is_bot": False, "first_name": "Nabil"},
         "chat": {"id": CHAT, "type": "private"}, "date": int(time.time()),
         "text": "خالتي اسمها إيه وبتسكن فين وبتشرب إيه؟"}}
try:
    urllib.request.urlopen(urllib.request.Request(W, data=json.dumps(body2).encode(),
                                                  headers={"Content-Type": "application/json"}), timeout=60)
    print("  ✅ السؤال اتبعت")
except Exception as e:
    print("  ❌", str(e)[:100])
time.sleep(90)
print("  الرد:", " ".join(psql("SELECT left(content,400) FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1").split())[:400])

print("\nDONE-LEARN")
