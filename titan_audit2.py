#!/usr/bin/env python3
"""فحص حرج: الذاكرة اللي بتتكتب فين، واللي المساعد بيقرا منها فين."""
import http.client, json, re, socket

SOCK = "/var/run/docker.sock"


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p

    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(300); sk.connect(s._p); s.sock = sk


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


cs = dk("GET", "/containers/json")
pg = [c for c in (cs or []) if "titan-titan-wqx9l7-postgres" in " ".join(c.get("Names") or [])][0]
env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m:
        env[m.group(1)] = m.group(2).strip()


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "export PGPASSWORD='%s'; psql -U %s -d %s -tAc \"%s\""
                              % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)])


print("=== المجموعات (collections) الموجودة ===")
print(psql("SELECT id||' | name='||name||' | items='||item_count||' | created='||to_char(created_at,'MM-DD HH24:MI') FROM memory_collections"))

print("\n=== العناصر بتتوزّع إزاي على المجموعات ===")
print(psql("SELECT c.name||' → '||count(i.id)||' عنصر' FROM memory_collections c LEFT JOIN memory_items i ON i.collection_id=c.id GROUP BY c.name"))

print("\n=== آخر الرسايل (المحادثة الحقيقية) ===")
print(psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI')||' ['||role||'] '||left(content,40),E'\\n') FROM (SELECT * FROM memory_messages ORDER BY created_at DESC LIMIT 6) t"))

print("\n=== الجلسات ===")
print(psql("SELECT string_agg(id||' ('||to_char(created_at,'MM-DD')||')', ', ') FROM (SELECT id, created_at FROM sessions ORDER BY created_at DESC LIMIT 4) t"))

print("\n=== الوكلاء (agents) ===")
print("  agent_profiles:", psql("SELECT count(*) FROM agent_profiles").strip())
print("  agent_runs آخر 5:", psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI'),' · ') FROM (SELECT created_at FROM agent_runs ORDER BY created_at DESC LIMIT 5) t"))
print("  إعدادات المساعد:", psql("SELECT string_agg(coalesce(name,'?')||'('||coalesce(model,'-')||')',', ') FROM (SELECT name, model FROM agent_profiles LIMIT 5) t")[:300])

print("\n=== المفاتيح والمستخدمين ===")
print("  users:", psql("SELECT string_agg(coalesce(email,'?')||'/'||coalesce(name,'?'),', ') FROM users"))
print("  api_keys:", psql("SELECT count(*) FROM api_keys").strip(), "· آخر استخدام:", psql("SELECT coalesce(max(last_used_at)::text,'مفيش') FROM api_keys").strip()[:20])

print("\n=== الجدول الزمني: آخر شغل حصل إمتى ===")
for tbl in ("heuristics", "synthesized_skills", "curiosity_explorations", "agent_runs", "memory_messages"):
    print("  %-24s آخر صف: %s" % (tbl, psql("SELECT coalesce(max(created_at)::text,'-') FROM %s" % tbl).strip()[:19]))

print("\nDONE-TITAN-AUDIT2")
