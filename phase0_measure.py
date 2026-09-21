#!/usr/bin/env python3
"""قياس سريع لمرحلة ٠: رسالتين + انتظار — مش محتاج وقت طويل.

الطريقة الطويلة (10 رسايل) بتُقتل لأن أي إعادة نشر بتقفل الحاوية.
الطريقة القصيرة دي بتخلص في دقايق فبتنجح.
"""
import http.client, json, re, socket, time, urllib.request

SOCK = "/var/run/docker.sock"
W = "https://titan.orcanox.xyz/telegram/webhook"
CHAT = 495185511

MSGS = [("سلام (متوقع خطوة واحدة)", "صباح الخير"),
        ("مهمة (متوقع 4 خطوات)", "اكتبلي دالة بايثون تقرا ملف وتجمع عمود")]


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(200); sk.connect(s._p); s.sock = sk


def dk(m, p, b=None):
    c = U(SOCK)
    c.request(m, p, body=json.dumps(b).encode() if b is not None else None,
              headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); raw = r.read(); c.close()
    try:
        return json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return raw.decode("utf-8", "ignore")


def exec_in(cid, cmd, wd="/"):
    ex = dk("POST", "/containers/%s/exec" % cid,
            {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": False, "WorkingDir": wd})
    eid = (ex or {}).get("Id")
    if not eid:
        return "(فشل)"
    c = U(SOCK)
    c.request("POST", "/exec/%s/start" % eid, body=json.dumps({"Detach": False, "Tty": False}).encode(),
              headers={"Content-Type": "application/json"})
    raw = c.getresponse().read(); c.close()
    out, i = [], 0
    while i + 8 <= len(raw):
        n = int.from_bytes(raw[i + 4:i + 8], "big")
        if n > len(raw) - i - 8:
            break
        out.append(raw[i + 8:i + 8 + n].decode("utf-8", "ignore")); i += 8 + n
    return ("".join(out) if out else raw.decode("utf-8", "ignore")).strip()


CS = dk("GET", "/containers/json")
pg = [c for c in (CS or []) if "titan-titan-wqx9l7-postgres" in " ".join(c.get("Names") or [])][0]
env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m:
        env[m.group(1)] = m.group(2).strip()


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "export PGPASSWORD='%s'; psql -U %s -d %s -tAc \"%s\""
                              % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)])


print("╔" + "═" * 76 + "╗")
print("║  قياس مرحلة ٠ (نداءات زيادة مقفولة)" + " " * 39 + "║")
print("╚" + "═" * 76 + "╝")

for i, (label, msg) in enumerate(MSGS, 1):
    uid = 9800 + i
    body = {"update_id": uid, "message": {"message_id": uid,
            "from": {"id": CHAT, "is_bot": False, "first_name": "Nabil", "language_code": "ar"},
            "chat": {"id": CHAT, "first_name": "Nabil", "type": "private"},
            "date": int(time.time()), "text": msg}}
    try:
        st = urllib.request.urlopen(urllib.request.Request(W, data=json.dumps(body).encode(),
                                                           headers={"Content-Type": "application/json"}), timeout=60).status
    except Exception as e:
        print("\n[%d] %s → فشل الإرسال: %s" % (i, label, str(e)[:60]))
        continue

    print("\n▸ [%d] %s" % (i, label))
    print("  الرسالة: «%s» · الويبهوك: %s" % (msg, st))
    # نستنى لحد 240 ثانية
    t0 = time.time()
    done = None
    while time.time() - t0 < 240:
        r = psql("SELECT coalesce(max(tokens_used)::text,'0')||'|'||coalesce(max(current_step)::text,'0')||'|'||"
                 "coalesce(max(status),'')||'|'||coalesce(round(max(extract(epoch from (updated_at-created_at))))::text,'0')||'|'||"
                 "coalesce(max(current_step)::text,'0') FROM agent_runs WHERE created_at > now() - interval '6 minutes' "
                 "AND prompt ILIKE '%%%s%%'" % msg[:20].replace("'", "''"))
        p = (r.strip().split("|") + ["0", "0", "", "0", "0"])[:5]
        if p[2] in ("completed", "failed") and p[0] != "0":
            done = p
            break
        time.sleep(15)
    if done:
        print("  ✅ خلصت: %s توكن · %s خطوة · %s · %s ثانية" % (done[0], done[1], done[2], done[3]))
    else:
        print("  ⏳ لسه شغالة (استنيت 4 دقايق)")
    reply = psql("SELECT left(content,200) FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1")
    cs = " ".join(reply.split())
    flag = "✅ سليم"
    if re.search(r"[\u4e00-\u9fff\uac00-\ud7af]", cs): flag = "❌ فيه صيني"
    elif len(cs) < 5: flag = "❌ فاضي"
    elif cs.startswith("{") or cs.startswith("["): flag = "❌ خام"
    print("  الرد: %s — %s" % (flag, cs[:170]))

print("\n" + "═" * 78)
print("للمقارنة (قبل مرحلة ٠):")
print("  «صباح الخير»  → 5 خطوات · 15,569 توكن · 72 ثانية")
print("  «اسمي إيه»    → 10 خطوات · 36,405 توكن")
print("  «دالة بايثون» → 10 خطوات · 60,652 توكن")
print("\nDONE-PHASE0-MEASURE")
