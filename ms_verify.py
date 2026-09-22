#!/usr/bin/env python3
"""تحقق من توصيل milliseconds.ai بتيتان — لازم يشتغل جوه كونتينر (له Docker socket).

بيفحص:
1) المفتاح واصل لبيئة الكور؟
2) الـAPI بيرد من جوه الشبكة؟
3) تيتان بيستخدم الأداة فعلًا لما تطلب منه استخراج؟
"""
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


def exec_in(cid, cmd, wd="/"):
    ex = dk("POST", "/containers/%s/exec" % cid,
            {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": False, "WorkingDir": wd})
    eid = (ex or {}).get("Id")
    if not eid: return "(فشل exec)"
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
names = lambda c: " ".join(c.get("Names") or [])
core = [c for c in CS if "titan" in names(c) and "core" in names(c)]
pg = [c for c in CS if "titan" in names(c) and "postgres" in names(c)]
print("containers: core=%d pg=%d" % (len(core), len(pg)))
if not core or not pg:
    print("❌ مش لاقي حاويات تيتان"); print("DONE-MS-VERIFY"); raise SystemExit

print("\n━━━ ① المفتاح + الـAPI من جوه حاوية الكور ━━━")
probe = (
    'test -n "$MILLISECONDS_API_KEY" && echo KEY_PRESENT || echo KEY_MISSING; '
    'node -e "'
    'const k=process.env.MILLISECONDS_API_KEY||"";'
    'fetch(\'https://api.milliseconds.ai/v1/decision-machine-1/extract\',{method:\'POST\','
    'headers:{\'Content-Type\':\'application/json\',Authorization:\'Bearer \'+k},'
    'body:JSON.stringify({text:\'نبيل كريم من ينبع ورقمه 0555123456\','
    'schema:{type:\'object\',properties:{الاسم:{type:\'string\'},المدينة:{type:\'string\'}}}})})'
    '.then(r=>r.text()).then(t=>console.log(\'API_OK\',t.slice(0,220)))'
    '.catch(e=>console.log(\'API_FAIL\',String(e).slice(0,150)));"'
)
print(exec_in(core[0]["Id"], ["sh", "-c", probe])[:700])

print("\n━━━ ② تيتان بيستخدم الأداة؟ (رسالة حقيقية) ━━━")
env = {}
for line in exec_in(pg[0]["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m: env[m.group(1)] = m.group(2).strip()


def psql(sql):
    return exec_in(pg[0]["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -tAc \"%s\""
                                 % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)])


msg = "استخرج لي الاسم والمدينة والرقم من النص ده: نبيل كريم من ينبع ورقمه 0555123456"
body = {"update_id": 9851, "message": {"message_id": 9851,
        "from": {"id": CHAT, "is_bot": False, "first_name": "Nabil"},
        "chat": {"id": CHAT, "type": "private"}, "date": int(time.time()), "text": msg}}
try:
    st = urllib.request.urlopen(urllib.request.Request(W, data=json.dumps(body).encode(),
                                                       headers={"Content-Type": "application/json"}), timeout=60).status
    print("  الويبهوك:", st)
except Exception as e:
    print("  ❌", str(e)[:120])

t0 = time.time(); res = None
while time.time() - t0 < 200:
    r = psql("SELECT coalesce(max(status),'')||'|'||coalesce(max(current_step)::text,'0')||'|'||"
             "coalesce(max(tokens_used)::text,'0')||'|'||"
             "coalesce(max(extract(epoch from (updated_at-created_at)))::text,'0') "
             "FROM agent_runs WHERE created_at > now() - interval '5 minutes' AND prompt ILIKE '%استخرج%'")
    p = (r.strip().split("|") + ["", "0", "0", "0"])[:4]
    if p[0] in ("completed", "failed") and p[2] != "0":
        res = p; break
    time.sleep(15)

if res:
    print("  ✅ %s توكن · %s خطوة · %s · %s ثانية" % (res[2], res[1], res[0], res[3]))
else:
    print("  ⏳ لسه (استنيت 200 ثانية)")

tools = psql("SELECT coalesce(string_agg(DISTINCT tool_name, ','),'(مفيش)') FROM agent_steps "
             "WHERE created_at > now() - interval '6 minutes'")
print("  الأدوات المستخدمة:", " ".join(tools.split())[:200])

rep = psql("SELECT left(content,500) FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1")
print("  الرد:", " ".join(rep.split())[:400])
print("\nDONE-MS-VERIFY")
