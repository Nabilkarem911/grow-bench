#!/usr/bin/env python3
"""تحديد تواريخ المشاكل: حديثة (بعد التحويل) ولا قديمة؟"""
import http.client, json, re, socket

SOCK = "/var/run/docker.sock"


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
rd = [c for c in (CS or []) if "titan-titan-wqx9l7-redis" in " ".join(c.get("Names") or [])]
env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m:
        env[m.group(1)] = m.group(2).strip()


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "export PGPASSWORD='%s'; psql -U %s -d %s -tAc \"%s\""
                              % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)])


print("⏰ الوقت الحالي في القاعدة:", psql("SELECT to_char(now(),'YYYY-MM-DD HH24:MI')").strip())
print("🔁 آخر إعادة نشر (بداية التحويل) ≈ 14:00")

print("\n【1】 العمليات المعلقة (16) — إمتى؟")
print(psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI')||' ['||current_step||'s] '||left(coalesce(prompt,''),30), E'\\n') FROM (SELECT created_at,current_step,prompt FROM agent_runs WHERE status IN ('running','pending') ORDER BY created_at DESC LIMIT 16) t"))

print("\n【2】 الرسايل الفاشلة (17) — إمتى؟")
print(psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI')||' '||left(coalesce(prompt,''),30), E'\\n') FROM (SELECT created_at,prompt FROM agent_runs WHERE status NOT IN ('completed') AND status NOT IN ('running','pending') ORDER BY created_at DESC LIMIT 17) t"))

print("\n【3】 الردود الفاضية — إمتى؟ (آخر 10)")
print(psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI')||' ['||role||'] '||length(content)||' حرف', E'\\n') FROM (SELECT created_at,role,content FROM memory_messages WHERE role='assistant' AND length(trim(content))<3 ORDER BY created_at DESC LIMIT 10) t"))

print("\n【4】 الرد اللي فيه صيني/تسريب — إمتى؟")
print(psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI')||' → '||left(content,120), E'\\n') FROM (SELECT created_at,content FROM memory_messages WHERE role='assistant' AND (content ~ '[\\u4e00-\\u9fff]' OR content ILIKE '%ds_safety%') ORDER BY created_at DESC LIMIT 5) t"))

print("\n【5】 الرسايل المكررة (63) — إمتى؟")
print(psql("SELECT string_agg(to_char(mn,'MM-DD HH24:MI')||' ×'||n||' '||left(c,40), E'\\n') FROM (SELECT min(created_at) mn, count(*) n, left(content,40) c FROM memory_messages GROUP BY session_id, role, content HAVING count(*)>1 ORDER BY n DESC LIMIT 8) t"))

print("\n【6】 بعد التحويل (آخر ساعتين): كل الرسايل")
print(psql("SELECT string_agg(to_char(created_at,'HH24:MI')||' | '||tokens_used||'t | '||current_step||'s | '||status||' | '||left(coalesce(prompt,''),28), E'\\n') FROM (SELECT * FROM agent_runs WHERE created_at > now() - interval '2 hours' ORDER BY created_at DESC) t"))

print("\n【7】 أخطاء core (آخر 5 أخطاء مفصلة)")
print(psql("SELECT 'نشوف لوجات الحاوية'").strip())
print("\nDONE-DATED-AUDIT")
