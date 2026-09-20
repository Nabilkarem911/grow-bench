#!/usr/bin/env python3
"""فحص تيتان الحقيقي: إيه اللي مستخدَم فعلًا وإيه اللي كلام (من قاعدة البيانات)."""
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
print("=== 1) حاويات تيتان الشغالة ===")
for c in (cs or []):
    nm = (c.get("Names") or [""])[0].lstrip("/")
    if "titan" in nm:
        print("   %-46s %s" % (nm[:44], c.get("Status")))

pg = [c for c in (cs or []) if "titan-titan-wqx9l7-postgres" in " ".join(c.get("Names") or [])]
if not pg:
    print("❌ مفيش postgres"); raise SystemExit
pg = pg[0]
env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m:
        env[m.group(1)] = m.group(2).strip()


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "export PGPASSWORD='%s'; psql -U %s -d %s -tAc \"%s\""
                              % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)])


print("\n=== 2) كل الجداول وعدد الصفوف (الأهم: إيه مستخدَم فعلًا) ===")
rows = psql("SELECT tablename||'|'||coalesce((xpath('/row/cnt/text()', query_to_xml('SELECT count(*) AS cnt FROM '||quote_ident(tablename), false, true, '')))[1]::text,'0') "
            "FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
used, empty = [], []
for line in rows.splitlines():
    if "|" not in line:
        continue
    name, cnt = line.strip().split("|", 1)
    try:
        n = int(cnt)
    except Exception:
        n = 0
    (used if n > 0 else empty).append((name, n))
print("\n  ✅ جداول فيها بيانات فعلية (%d):" % len(used))
for nm, n in sorted(used, key=lambda x: -x[1]):
    print("     %-44s %d صف" % (nm[:44], n))
print("\n  ⚠️ جداول فاضية تمامًا (%d) — دي حزم/خواص اتبنت وما اتستخدمتش:" % len(empty))
print("     " + " · ".join(nm for nm, _ in empty[:60]))

print("\n=== 3) آخر استخدام حقيقي (المحادثات) ===")
print("  آخر 5 محادثات:", psql("SELECT string_agg(to_char(created_at,'MM-DD HH24:MI'),' · ') FROM (SELECT created_at FROM memory_messages ORDER BY created_at DESC LIMIT 5) t"))
print("  عدد الرسايل:", psql("SELECT count(*) FROM memory_messages").strip())
print("  قنوات/جلسات:", psql("SELECT count(DISTINCT session_id) FROM memory_messages").strip())

print("\n=== 4) الأدوات المتاحة للمساعد ===")
print(psql("SELECT string_agg(DISTINCT tool_name,', ') FROM (SELECT jsonb_array_elements_text(coalesce(metadata->'tools','[]'::jsonb)) AS tool_name FROM agent_runs LIMIT 200) t").strip()[:400])

print("\n=== 5) حالة التشغيل (آخر runs) ===")
print(psql("SELECT coalesce(status,'?')||' = '||count(*) FROM agent_runs GROUP BY status"))
print("\nDONE-TITAN-AUDIT")
