#!/usr/bin/env python3
"""تحليل الأربع اختبارات: زمن، توكنات، خطوات، أخطاء، وسبب التأخير."""
import http.client, json, re, socket

SOCK = "/var/run/docker.sock"


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p

    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(240); sk.connect(s._p); s.sock = sk


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


print("=== أعمدة agent_steps ===")
print("  " + psql("SELECT string_agg(column_name,', ') FROM information_schema.columns WHERE table_name='agent_steps'").strip())

print("\n=== 1) آخر 8 رسائل (الزمن الكامل + توكنات + خطوات) ===")
print(psql("SELECT string_agg(to_char(created_at,'HH24:MI:SS')||' → '||to_char(updated_at,'HH24:MI:SS')||'  =  '||round(extract(epoch from (updated_at-created_at)))::text||' ث | '||tokens_used||'t | '||current_step||'s | '||status||' | '||left(coalesce(prompt,''),32), E'\\n') FROM (SELECT * FROM agent_runs WHERE created_at > now() - interval '3 hours' ORDER BY created_at DESC LIMIT 8) t"))

print("\n=== 2) تفصيل كل خطوة (زمن + توكنات) لآخر 5 رسائل ===")
print(psql("""
SELECT string_agg(txt, E'\\n') FROM (
  SELECT r.created_at, s.run_id, s.index,
         '  '||to_char(r.created_at,'HH24:MI')||' ['||left(coalesce(r.prompt,''),22)||'] خطوة '||s.index||': '||
         coalesce(s.latency_ms::text,'?')||'ms · '||coalesce(s.tokens_used::text,'0')||' توكن · '||
         coalesce(s.status,'?')||' · '||left(coalesce(s.tool_name, s.thought, s.reflection, ''),55) AS txt
  FROM agent_steps s JOIN agent_runs r ON r.id = s.run_id
  WHERE r.created_at > now() - interval '3 hours'
  ORDER BY r.created_at DESC, s.index ASC LIMIT 40
) q
"""))

print("\n=== 3) الأدوات اللي اتستخدمت ===")
print(psql("""
SELECT string_agg(tool||' ×'||n, ' · ') FROM (
  SELECT coalesce(s.tool_name,'(بدون)') AS tool, count(*) n
  FROM agent_steps s JOIN agent_runs r ON r.id=s.run_id
  WHERE r.created_at > now() - interval '3 hours' GROUP BY 1 ORDER BY 2 DESC LIMIT 10
) t
"""))

print("\n=== 4) الأخطاء في الخطوات ===")
print(psql("""
SELECT string_agg(to_char(r.created_at,'HH24:MI')||' خطوة '||s.index||': '||left(coalesce(s.error, s.status,''),90), E'\\n')
FROM agent_steps s JOIN agent_runs r ON r.id=s.run_id
WHERE r.created_at > now() - interval '3 hours' AND (s.error IS NOT NULL OR s.status NOT IN ('completed'))
LIMIT 10
"""))

print("\n=== 5) الردود النهائية (آخر 5) ===")
print(psql("SELECT string_agg('▸ '||to_char(created_at,'HH24:MI')||': '||left(replace(coalesce(final_answer,'(فاضي)'),E'\\n',' '),200), E'\\n') FROM (SELECT created_at, final_answer FROM agent_runs WHERE created_at > now() - interval '3 hours' ORDER BY created_at DESC LIMIT 5) t"))

print("\n=== 6) هل فيه صيني/فاضي؟ ===")
print(psql("SELECT 'صيني: '||count(*) FILTER (WHERE content ~ '[\\u4e00-\\u9fff]')||' · فاضي: '||count(*) FILTER (WHERE length(trim(content))<3)||' · تسريب: '||count(*) FILTER (WHERE content ILIKE '%ds_safety%') FROM (SELECT content FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 8) t"))

print("\n═══════ تشخيص سبب التأخير ═══════")
print("مقارنة: زمن كل خطوة مقابل زمن الـAPI الخارجي")
print(psql("""
SELECT 'متوسط زمن الخطوة: '||round(avg(s.latency_ms))::text||'ms · أقصى: '||max(s.latency_ms)::text||'ms · عدد: '||count(*)::text
FROM agent_steps s JOIN agent_runs r ON r.id=s.run_id
WHERE r.created_at > now() - interval '3 hours' AND s.latency_ms IS NOT NULL
"""))

print("\nDONE-4TESTS")
