#!/usr/bin/env python3
"""قياس استهلاك الكوتا الحقيقي — نسخة تكتشف الأعمدة بنفسها."""
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


print("=== 0) أعمدة agent_runs ===")
cols = psql("SELECT string_agg(column_name,', ') FROM information_schema.columns WHERE table_name='agent_runs'")
print("  " + cols.strip())

tok_col = "tokens_used" if "tokens_used" in cols else ("tokensUsed" if "tokensUsed" in cols else None)
step_col = None
for c in ("steps", "step_count", "steps_count", "total_steps"):
    if c in cols:
        step_col = c
        break

print("\n=== 1) الاستهلاك الحقيقي لكل رسالة ===")
if tok_col:
    print("  " + psql("SELECT 'عدد: '||count(*)||' | المتوسط: '||round(avg(%s))||' | أقل: '||min(%s)||' | أعلى: '||max(%s)||' | الوسيط: '||round(percentile_cont(0.5) WITHIN GROUP (ORDER BY %s)) FROM agent_runs WHERE %s > 0" % (tok_col, tok_col, tok_col, tok_col, tok_col)).strip())
    print("\n=== 2) آخر 12 رسالة ===")
    print(psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI')||' → '||%s||' توكن', E'\\n') FROM (SELECT created_at, %s FROM agent_runs WHERE %s>0 ORDER BY created_at DESC LIMIT 12) t" % (tok_col, tok_col, tok_col)))
else:
    print("  ⚠️ مفيش عمود توكنات")

print("\n=== 3) أحجام حقيقية (حروف) ===")
print("  " + psql("SELECT 'متوسط رسالة المستخدم: '||round(avg(length(content)))||' حرف | متوسط الرد: '||round(avg(length(content))) FROM memory_messages WHERE role='user'").strip())

print("\n=== 4) كل البيانات عن التوكنات في أي جدول ===")
for t in ("agent_runs", "benchmark_results", "meta_learning_results", "hyper_agent_performance", "sessions", "memory_messages"):
    c = psql("SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='%s' AND (column_name ILIKE '%%token%%' OR column_name ILIKE '%%cost%%' OR column_name ILIKE '%%usage%%')" % t)
    if c.strip():
        print("  %-26s → %s" % (t, c.strip()))

print("\n=== 5) لو فيه بيانات استخدام فعلية ===")
print("  agent_runs فيها قيم:", psql("SELECT count(*) FROM agent_runs WHERE %s > 0" % tok_col) if tok_col else "?")
print("  sessions:", psql("SELECT count(*) FROM sessions").strip(), "· memory_messages:", psql("SELECT count(*) FROM memory_messages").strip())

print("\nDONE-QUOTA-AUDIT2")
