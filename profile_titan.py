#!/usr/bin/env python3
"""قياس طبقي لمسار تيتان: من ويب هوك تيليجرام لحد الرد — من غير لمس الكود.

الطريقة (قراءة فقط):
  T0 نبعث رسالة      T1 الويبهوك يرد      T2 الـrun يتخلق
  T3 أول خطوة تبدأ   T4 الخطوة تخلص       T5 الـrun يخلص
  T6 الرد يتخزن      T7 إحنا نشوفه

الفرق بين التواريخ ده = زمن كل طبقة (الطابور / بناء السياق / الموديل / الحفظ).
+ موارد الحاويات من Docker stats (CPU/RAM).
"""
import http.client, json, os, re, socket, time, urllib.request

SOCK = "/var/run/docker.sock"
W = "https://titan.orcanox.xyz/telegram/webhook"
CHAT = 495185511

MSG = "صباح الخير"


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(300); sk.connect(s._p); s.sock = sk


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
nm = lambda c: " ".join(c.get("Names") or [])
pg = [c for c in CS if "titan" in nm(c) and "postgres" in nm(c)][0]
titan_containers = [c for c in CS if "titan" in nm(c)]
env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m: env[m.group(1)] = m.group(2).strip()
P, UU, DB = env.get("PASSWORD", ""), env.get("USER", ""), env.get("DB", "")


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -tAc \"%s\"" % (P, UU, DB, sql)])


def stats(cid):
    s = dk("GET", "/containers/%s/stats?stream=false" % cid)
    try:
        cpu = s["cpu_stats"]
        pre = s["precpu_stats"]
        cd = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
        sd = cpu["system_cpu_usage"] - pre["system_cpu_usage"]
        ncpu = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage") or [1])
        pct = (cd / sd * ncpu * 100.0) if sd else 0.0
        mem = s["memory_stats"].get("usage", 0) / 1048576.0
        lim = s["memory_stats"].get("limit", 0) / 1048576.0
        return round(pct, 1), round(mem), round(lim)
    except Exception:
        return None, None, None


print("█" * 78)
print("█  القياس الطبقي — المسار الحالي (قراءة فقط، مفيش أي تعديل)")
print("█" * 78)

print("\n━━━ ① موارد حاويات تيتان (قبل) ━━━")
for c in titan_containers:
    n = nm(c).replace("/", "")
    pct, mem, lim = stats(c["Id"])
    if pct is not None:
        print("  %-40s CPU=%-6s%%  RAM=%s/%s MB" % (n[:40], pct, mem, lim))

print("\n━━━ ② نبعث «%s» ونسجّل كل نقطة زمن ━━━" % MSG)
uid = 9950
body = {"update_id": uid, "message": {"message_id": uid,
        "from": {"id": CHAT, "is_bot": False, "first_name": "Nabil"},
        "chat": {"id": CHAT, "type": "private"}, "date": int(time.time()), "text": MSG}}
T0 = time.time()
try:
    r = urllib.request.urlopen(urllib.request.Request(
        W, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}), timeout=60)
    T1 = time.time()
    print("  T0 إرسال → T1 الويبهوك رد: %.2f ثانية (كود %s)" % (T1 - T0, r.status))
except Exception as e:
    T1 = time.time()
    print("  ❌ الويبهوك:", str(e)[:120])

# ندوّر على الـrun
run = None
t_poll0 = time.time()
while time.time() - t_poll0 < 60:
    rid = psql("SELECT id||'|'||extract(epoch from created_at)::text FROM agent_runs "
               "WHERE prompt ILIKE '%%صباح الخير%%' ORDER BY created_at DESC LIMIT 1").strip()
    if rid and "|" in rid:
        run = rid.split("|")
        break
    time.sleep(1)

if not run:
    print("  ❌ مش لاقي الـrun"); print("DONE-PROFILE"); raise SystemExit
run_id, run_created = run[0], float(run[1])
print("  T2 الـrun اتخلق: %.2f ثانية بعد الإرسال" % (run_created - T0))

# نتبع الخطوات + الإنهاء
steps = []
t_done = None
t_poll = time.time()
while time.time() - t_poll < 300:
    st = psql("SELECT coalesce(status,'')||'|'||extract(epoch from updated_at)::text||'|'||"
              "coalesce(latency_ms::text,'0')||'|'||coalesce(tokens_used::text,'0')||'|'||"
              "coalesce(index::text,'0') FROM agent_steps WHERE run_id='%s' ORDER BY index" % run_id)
    rows = [l for l in st.splitlines() if l.strip()]
    rstat = psql("SELECT status||'|'||extract(epoch from updated_at)::text FROM agent_runs WHERE id='%s'" % run_id).strip()
    if rstat and "|" in rstat:
        s, u = rstat.split("|")[0], float(rstat.split("|")[1])
        if s in ("completed", "failed"):
            t_done = u; steps = rows; break
    time.sleep(2)

print("\n━━━ ③ خطوات التفكير (agent loop) ━━━")
if steps:
    print("  عدد الخطوات: %d" % len(steps))
    for line in steps:
        p = line.split("|")
        idx = p[4] if len(p) > 4 else "?"
        lat = p[2] if len(p) > 2 else "0"
        tok = p[3] if len(p) > 3 else "0"
        print("   خطوة %s: %s · موديل %s مللي · %s توكن" % (idx, p[0] if p else "?", lat, tok))
    total_lat = sum(int(x.split("|")[2] or 0) for x in steps)
    total_tok = sum(int(x.split("|")[3] or 0) for x in steps)
    print("  إجمالي زمن الموديل: %s مللي (%.2f ثانية)" % (total_lat, total_lat / 1000))
    print("  إجمالي التوكنات: %s" % total_tok)
else:
    print("  (مفيش خطوات مسجّلة)")

print("\n━━━ ④ الرد + نقطة التوفر ━━━")
t_seen = time.time()
msg_t = psql("SELECT extract(epoch from created_at)::text||'|'||left(content,80) FROM memory_messages "
             "WHERE role='assistant' AND created_at > now() - interval '10 minutes' ORDER BY created_at DESC LIMIT 1").strip()
if msg_t and "|" in msg_t:
    mt, content = msg_t.split("|", 1)
    print("  T6 الرد اتخزن: %.2f ثانية بعد الإرسال" % (float(mt) - T0))
    print("  الرد:", " ".join(content.split())[:150])

print("\n━━━ ⑤ تفصيل الطبقات ━━━")
if t_done:
    T5 = t_done
    print("  T0→T1  ويب هوك              %.2f ث" % (T1 - T0))
    print("  T1→T2  **الطابور/الجدولة**   %.2f ث" % (run_created - T1))
    if steps:
        first = steps[0].split("|")
        last = steps[-1].split("|")
        model_ms = sum(int(x.split("|")[2] or 0) for x in steps) / 1000.0
        print("  T2→T5  **كل الـagent**        %.2f ث" % (T5 - run_created))
        print("      ├─ نداءات الموديل       %.2f ث (%.0f%%)" % (model_ms, model_ms / max(T5 - run_created, 0.01) * 100))
        print("      └─ **شغل تيتان نفسه**    %.2f ث (%.0f%%) ← ده اللي بيتقاس" % (
            (T5 - run_created) - model_ms, ((T5 - run_created) - model_ms) / max(T5 - run_created, 0.01) * 100))
    print("  T0→T5  **الإجمالي لحد ما الـrun خلص**  %.2f ث" % (T5 - T0))
    if msg_t and "|" in msg_t:
        print("  T5→T6  حفظ الرد            %.2f ث" % (float(msg_t.split("|")[0]) - T5))
    print("  T0→T6  **الإجمالي لحد ما المستخدم يشوف**  %.2f ث" % (float(msg_t.split("|")[0]) - T0 if msg_t and "|" in msg_t else T5 - T0))

print("\n━━━ ⑥ موارد تيتان (بعد) ━━━")
for c in titan_containers:
    n = nm(c).replace("/", "")
    pct, mem, lim = stats(c["Id"])
    if pct is not None:
        print("  %-40s CPU=%-6s%%  RAM=%s/%s MB" % (n[:40], pct, mem, lim))

print("\nDONE-PROFILE")
