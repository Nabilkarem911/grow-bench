#!/usr/bin/env python3
"""تنضيف تيتان — نسخة احتياطية + فحص (dry-run) + إصلاح آمن.

⚠️ القواعد:
 - بسمة احتياطية كاملة الأول (pg_dump) — مفيش تعديل قبلها
 - الحذف dry-run: نعرض بالظبط اللي هيتشال، والتنفيذ في خطوة تانية
 - الإصلاحات الآمنة بس (الـ42 المعلّقين) بتتنفذ دلوقتي
 - الجداول الفاضية: **مش بنلمسها** (خطر بلا داعي)
"""
import base64, http.client, json, os, re, socket, time, urllib.request

SOCK = "/var/run/docker.sock"
TOK = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT = 495185511


def tg(text):
    if not TOK: return
    try:
        urllib.request.urlopen(urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % TOK,
            data=json.dumps({"chat_id": CHAT, "text": text}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}), timeout=30)
    except Exception: pass


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
env = {}
for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
    m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
    if m: env[m.group(1)] = m.group(2).strip()
P, UU, DB = env.get("PASSWORD", ""), env.get("USER", ""), env.get("DB", "")


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -tAc \"%s\"" % (P, UU, DB, sql)])


def psql_file(sql):
    exec_in(pg["Id"], ["sh", "-c", "cat > /tmp/op.sql <<'SQLEOF'\n%s\nSQLEOF" % sql])
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -q -f /tmp/op.sql 2>&1 | tail -6" % (P, UU, DB)])


print("█" * 78)
print("█  ① النسخة الاحتياطية الكاملة (قبل أي تعديل)")
print("█" * 78)
print(exec_in(pg["Id"], ["sh", "-c",
                         "mkdir -p /tmp/bk2 && PGPASSWORD='%s' pg_dump -U %s -d %s -Fc "
                         "-f /tmp/bk2/titan_full.dump 2>/dev/null; ls -la /tmp/bk2/titan_full.dump" % (P, UU, DB)])[:300])

# نرفع نسخة نصية مضغوطة (الـdump المضغوط ثنائي — نرفع النصي)
print(exec_in(pg["Id"], ["sh", "-c",
                         "PGPASSWORD='%s' pg_dump -U %s -d %s > /tmp/bk2/titan_text.sql 2>/dev/null; "
                         "gzip -c /tmp/bk2/titan_text.sql > /tmp/bk2/titan_text.sql.gz; "
                         "ls -la /tmp/bk2/titan_text.sql.gz" % (P, UU, DB)])[:300])

raw = exec_in(pg["Id"], ["sh", "-c", "base64 -w0 /tmp/bk2/titan_text.sql.gz"])
b64 = "".join(raw.split())
gh = os.environ.get("GITHUB_TOKEN", "")
if gh and b64:
    api = "https://api.github.com/repos/Nabilkarem911/grow-bench/contents/results/titan_full_backup.sql.gz"
    hdr = {"Authorization": "Bearer " + gh, "Accept": "application/vnd.github+json", "User-Agent": "fawkes"}
    sha = None
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60)); sha = d.get("sha")
    except Exception: pass
    body = {"message": "backup: full titan db before cleanup", "content": b64}
    if sha: body["sha"] = sha
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(api, data=json.dumps(body).encode(), headers=hdr, method="PUT"), timeout=300))
        print("  ✅ النسخة الكاملة على GitHub:", r.get("content", {}).get("path"), "(%.1f MB)" % (len(b64) * 0.75 / 1048576))
    except Exception as e:
        print("  ⚠️ رفع النسخة:", str(e)[:150])
        print("  ℹ️ النسخة المضغوطة محفوظة جوه الكونتينر: /tmp/bk2/titan_text.sql.gz")

print("\n" + "█" * 78)
print("█  ② عناصر «running» المعلّقة (تواريخ صغيرة)")
print("█" * 78)
stuck = psql("SELECT count(*) FROM agent_runs WHERE status='running' AND created_at < now() - interval '48 hours'")
print("  معلّقة أكتر من 48 ساعة:", stuck.strip())
print("  أقدمهم:")
for line in psql("SELECT to_char(created_at,'YYYY-MM-DD') || ' ┃ ' || coalesce(left(prompt,60),'') FROM agent_runs "
                 "WHERE status='running' AND created_at < now() - interval '48 hours' ORDER BY created_at LIMIT 8").splitlines():
    if line.strip(): print("   ", line[:100])

print("\n" + "█" * 78)
print("█  ③ فحص التكرار (dry-run — مفيش حذف)")
print("█" * 78)
tabs = [t.strip() for t in psql(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name").splitlines() if t.strip()]
print("  الجداول في القاعدة:", len(tabs))
dups = []
for t in tabs:
    try:
        c = psql("SELECT count(*) FROM %s" % t).strip()
        if not c.isdigit() or int(c) < 500: continue
        # ندوّر على عمود نصي للتكرار
        col = psql("SELECT column_name FROM information_schema.columns WHERE table_name='%s' "
                   "AND data_type IN ('text','character varying') ORDER BY ordinal_position LIMIT 1" % t).strip()
        if not col: continue
        d = psql("SELECT count(*) FROM (SELECT %s FROM %s GROUP BY %s HAVING count(*)>1) x" % (col, t, col)).strip()
        dup = psql("SELECT count(*) FROM %s" % t).strip()
        if d.isdigit() and int(d) > 0:
            dups.append((t, col, int(c), int(d), dups and 0 or 0))
    except Exception:
        pass

# نعيد الترتيب ونطبع
if dups:
    print("  جداول فيها تكرار:")
    for t, col, c, d, _ in sorted(dups, key=lambda x: -x[3])[:8]:
        extra = psql("SELECT count(*) FROM (SELECT %s FROM %s GROUP BY %s) x" % (col, t, col)).strip()
        print("   %-28s صفوف=%-7s مجموعات فريدة=%-7s مجموعات مكررة=%s" % (t, c, extra, d))
else:
    print("  (مفيش جداول كبيرة فيها تكرار)")

print("\n" + "█" * 78)
print("█  ④ الإصلاح الآمن: تحويل المعلّقين لـ«failed» بسبب واضح")
print("█" * 78)
n = stuck.strip()
if n.isdigit() and int(n) > 0:
    r = psql_file("UPDATE agent_runs SET status='failed', updated_at=now(), "
                  "error='stale run auto-closed during memory cleanup 2026-09' "
                  "WHERE status='running' AND created_at < now() - interval '48 hours';")
    print("  ", r[:200])
    print("  بعد الإصلاح — معلّقين:", psql("SELECT count(*) FROM agent_runs WHERE status='running' AND created_at < now() - interval '48 hours'").strip())
else:
    print("  مفيش معلّقين ✅")

print("\n" + "█" * 78)
print("█  ⑤ الحالة النهائية")
print("█" * 78)
for t in ("agent_runs", "memory_items", "user_context", "memory_messages"):
    print("  %-20s %s" % (t, psql("SELECT count(*) FROM %s" % t).strip()))
print("  سجل التعديل: استخدمنا WHERE بشرط صريح (status + 48 ساعة) — مفيش حذف")

print("\nDONE-CLEAN")
