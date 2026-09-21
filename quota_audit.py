#!/usr/bin/env python3
"""قياس استهلاك الكوتا الحقيقي لكل رسالة في تيتان (من بياناته نفسها)."""
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


print("=== 1) استهلاك التوكنات الحقيقي لكل رسالة (من agent_runs) ===")
print(psql("SELECT 'عدد الرسايل المقاسة: '||count(*)||' | المتوسط: '||round(avg(\"tokensUsed\"))||' | أقل: '||min(\"tokensUsed\")||' | أعلى: '||max(\"tokensUsed\")||' | الوسيط: '||round(percentile_cont(0.5) WITHIN GROUP (ORDER BY \"tokensUsed\")) FROM agent_runs WHERE \"tokensUsed\" > 0"))

print("\n=== 2) آخر 15 رسالة (توكنات + خطوات) ===")
print(psql("SELECT to_char(created_at,'MM-DD HH24:MI')||' | '||coalesce(\"tokensUsed\",0)||' توكن | '||coalesce(steps,0)||' خطوة | '||coalesce(status,'?') FROM agent_runs WHERE \"tokensUsed\" > 0 ORDER BY created_at DESC LIMIT 15"))

print("\n=== 3) حجم الرسايل الفعلي (مش التوكنات — عدد الحروف) ===")
print(psql("SELECT 'متوسط حروف رسالة المستخدم: '||round(avg(length(content)))||' | متوسط رد المساعد: '||round(avg(length(content))) FROM memory_messages WHERE role='user'"))
print(psql("SELECT 'أطول رسالة مستخدم: '||max(length(content))||' حرف' FROM memory_messages WHERE role='user'"))

print("\n=== 4) حجم الذاكرة المحقونة (اللي بيتحوّل لبرومبت) ===")
print(psql("SELECT 'متوسط طول عنصر ذاكرة: '||round(avg(length(content)))||' حرف | الإجمالي: '||sum(length(content))||' حرف' FROM memory_items"))
print(psql("SELECT 'أكبر عنصر: '||max(length(content))||' حرف' FROM memory_items"))

print("\n=== 5) عدد الخطوات (كل خطوة = نداء للـAPI) ===")
print(psql("SELECT 'متوسط الخطوات: '||round(avg(steps),1)||' | أقصى: '||max(steps) FROM agent_runs WHERE steps > 0"))
print(psql("SELECT coalesce(steps,0)||' خطوة → '||count(*)||' مرة' FROM agent_runs WHERE \"tokensUsed\">0 GROUP BY steps ORDER BY steps DESC LIMIT 8"))

print("\n=== 6) الأدوات المُستخدمة (كل أداة = دور إضافي) ===")
print(psql("SELECT 'إجمالي استخدامات الأدوات: '||coalesce(sum(calls),0) FROM tool_execution_stats").strip() or "  (فاضي)")

print("\nDONE-QUOTA-AUDIT")
