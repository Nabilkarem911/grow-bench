#!/usr/bin/env python3
"""نقرا آخر رد من تيتان + استهلاكه."""
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


print("=== 1) آخر 3 رسايل (الوقت + التوكنات + الخطوات) ===")
print(psql("SELECT to_char(created_at,'HH24:MI:SS')||' | '||tokens_used||' توكن | '||current_step||' خطوة | '||status||' | '||left(coalesce(prompt,''),40) FROM agent_runs WHERE tokens_used>0 ORDER BY created_at DESC LIMIT 3"))

print("\n=== 2) آخر رد فعلي من المساعد (أول 400 حرف) ===")
print(psql("SELECT content FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1"))

print("\n=== 3) آخر رسالة منك ===")
print(psql("SELECT to_char(created_at,'HH24:MI:SS')||' → '||content FROM memory_messages WHERE role='user' ORDER BY created_at DESC LIMIT 1"))

print("\n=== 4) هل فيه صيني في الرد؟ ===")
print(psql("SELECT CASE WHEN content ~ '[\\u4e00-\\u9fff]' THEN '❌ فيه صيني!' ELSE '✅ مفيش صيني' END FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1"))

print("\n=== 5) إجمالي عناصر الذاكرة (بعد كل الشغل) ===")
print("  " + psql("SELECT count(*) FROM memory_items").strip())

print("\nDONE-REPLY-CHECK")
