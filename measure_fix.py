#!/usr/bin/env python3
"""قياس أثر تقليل الخطوات على استهلاك التوكنات (قبل/بعد)."""
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


print("=== 1) آخر 12 رسالة (بالتوكنات والخطوات) ===")
print(psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI')||' | '||tokens_used||' توكن | '||current_step||' خطوة | '||left(coalesce(prompt,''),28), E'\\n') FROM (SELECT created_at,tokens_used,current_step,prompt FROM agent_runs WHERE tokens_used>0 ORDER BY created_at DESC LIMIT 12) t"))

print("\n=== 2) قبل الإصلاح (كل الرسايل الأقدم) ===")
print("  " + psql("SELECT 'عدد: '||count(*)||' | المتوسط: '||round(avg(tokens_used))||' | الوسيط: '||round(percentile_cont(0.5) WITHIN GROUP (ORDER BY tokens_used)) FROM agent_runs WHERE tokens_used>0 AND created_at < now() - interval '3 hours'").strip())

print("\n=== 3) بعد الإصلاح (آخر 3 ساعات) ===")
r = psql("SELECT 'عدد: '||count(*)||' | المتوسط: '||coalesce(round(avg(tokens_used))::text,'-')||' | الوسيط: '||coalesce(round(percentile_cont(0.5) WITHIN GROUP (ORDER BY tokens_used))::text,'-') FROM agent_runs WHERE tokens_used>0 AND created_at > now() - interval '3 hours'")
print("  " + r.strip())

print("\n=== 4) عدد الخطوات: قبل وبعد ===")
print("  قبل:", psql("SELECT 'متوسط '||round(avg(current_step),1)||' · أقصى '||max(current_step) FROM agent_runs WHERE tokens_used>0 AND created_at < now() - interval '3 hours'").strip())
print("  بعد:", psql("SELECT 'متوسط '||coalesce(round(avg(current_step),1)::text,'-')||' · أقصى '||coalesce(max(current_step)::text,'-') FROM agent_runs WHERE tokens_used>0 AND created_at > now() - interval '3 hours'").strip())

print("\n=== 5) آخر رسالة بالتفصيل ===")
print(psql("SELECT 'الوقت: '||to_char(created_at,'HH24:MI:SS')||E'\\n'||'توكنات: '||tokens_used||E'\\n'||'خطوات: '||current_step||E'\\n'||'الحالة: '||status||E'\\n'||'السؤال: '||left(coalesce(prompt,''),100) FROM agent_runs WHERE tokens_used>0 ORDER BY created_at DESC LIMIT 1"))

print("\nDONE-AFTER-FIX")
