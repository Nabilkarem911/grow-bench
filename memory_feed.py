#!/usr/bin/env python3
"""تنضيف الذاكرة من معلومات الاختبار + تغذيتها بمعلومات نبيل الحقيقية.

قواعد الأمان:
 - النسخة الاحتياطية اتعملت قبل (results/titan_memory_backup.sql) ✓
 - الحذف بأنماط محددة بالاسم بس (مش حذف عشوائي) ✓
 - كل حذف بيُطبع قبل/بعد → أثر مراجعة ✓
"""
import base64, http.client, json, os, re, socket, urllib.request

SOCK = "/var/run/docker.sock"

# المعلومات الحقيقية (من ملف نبيل المرجعي — متحققة)
REAL = [
    ("name",           "نبيل كريم"),
    ("city",           "ينبع، السعودية"),
    ("job",            "موظف في مؤسسة مطاعم عميد البحارة (موظف، مش المالك)"),
    ("age",            "36 سنة"),
    ("role",           "مطور Full Stack"),
    ("wife",           "سماح حمدي عبد المقصود النجار"),
    ("son",            "كنان نبيل — مواليد 7/2022"),
    ("family_visits",  "عيلته بتزوره من طنطا (مصر) عن طريق MOFA السعودية + تساهيل"),
    ("style",          "بيحب المصري في الكلام والأرقام بالبلدي — مش الفصحى"),
    ("prefers",        "القياس الحقيقي مش النظري · اختبار قبل/بعد · مفيش فروع جانبية"),
    ("dislikes",       "الادعاءات غير المؤكدة · التخمين في الألوان/الهوية"),
    ("projects_tools", "حروفي (Flutter أطفال) · رفيق · تيتان · مرصد الذهب · Smart Cloud Screen · QR Menu · grow · InferMesh · gpacksa"),
    ("servers",        "84.8.106.69 (Hermes + Dokploy) · 187.127.76.226 (شغل)"),
    ("workflow",       "Windsurf + Devin للتنفيذ · فوكس (Hermes) مستشار ومقرر تقني"),
]

# أنماط المعلومات الوهمية (من الاختبارات)
FAKE = ["فاطمة", "مصطفى", "أكبر أقمار", "زحل", "نيكست فيت", "NextFit", "الشاي بالنعناع"]
# مفاتيح وهمية بالاسم (من الاختبارات) — بتتشال كلها
FAKE_KEYS = ["aunt", "brother", "favorite_drink", "workplace"]


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p
    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(200); sk.connect(s._p); s.sock = sk


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
    """للنصوص الطويلة/العربي — ملف مش وسيط شل."""
    exec_in(pg["Id"], ["sh", "-c", "cat > /tmp/op.sql <<'SQLEOF'\n%s\nSQLEOF" % sql])
    return exec_in(pg["Id"], ["sh", "-c", "PGPASSWORD='%s' psql -U %s -d %s -q -f /tmp/op.sql 2>&1 | tail -5" % (P, UU, DB)])


print("█" * 78)
print("█  ① قبل التنضيف")
print("█" * 78)
owner = psql("SELECT owner_id FROM user_context WHERE key='brother' LIMIT 1").strip()
if not owner:
    owner = psql("SELECT owner_id FROM user_context GROUP BY owner_id ORDER BY count(*) DESC LIMIT 1").strip()
print("  المالك (owner_id):", owner)
print("  صفوف user_context:", psql("SELECT count(*) FROM user_context").strip())
print("  عناصر memory_items:", psql("SELECT count(*) FROM memory_items").strip())
for p in FAKE:
    print("   وهمي «%s» → user_context=%s · memory_items=%s"
          % (p, psql("SELECT count(*) FROM user_context WHERE value ILIKE '%%%s%%'" % p).strip(),
             psql("SELECT count(*) FROM memory_items WHERE content ILIKE '%%%s%%'" % p).strip()))

print("\n" + "█" * 78)
print("█  ② الحذف (أنماط محددة بس)")
print("█" * 78)
tot = 0
for p in FAKE:
    a = psql("SELECT count(*) FROM user_context WHERE value ILIKE '%%%s%%'" % p).strip()
    b = psql("SELECT count(*) FROM memory_items WHERE content ILIKE '%%%s%%'" % p).strip()
    if a not in ("0", ""):
        psql_file("DELETE FROM user_context WHERE value ILIKE '%%%s%%';" % p)
    if b not in ("0", ""):
        psql_file("DELETE FROM memory_items WHERE content ILIKE '%%%s%%';" % p)
    print("  «%s»: اتمسح %s من user_context و %s من memory_items" % (p, a, b))
    tot += int(a or 0) + int(b or 0)

# مفاتيح وهمية صريحة
for k in FAKE_KEYS:
    c = psql("SELECT count(*) FROM user_context WHERE key='%s'" % k).strip()
    if c not in ("0", ""):
        psql_file("DELETE FROM user_context WHERE key='%s';" % k)
        print("  مفتاح وهمي «%s»: اتمسح %s صف" % (k, c))
        tot += int(c or 0)

# صفوف فاضية القيمة (نفاية)
z = psql("SELECT count(*) FROM user_context WHERE value IS NULL OR trim(value)=''").strip()
if z not in ("0", ""):
    psql_file("DELETE FROM user_context WHERE value IS NULL OR trim(value)='';")
    print("  صفوف فاضية: اتمسحت", z)
    tot += int(z or 0)

# مفتاحي اليومي (زيادة مش محتاجة — تيتان عنده ميكانيزم أحسن)
mine = psql("SELECT count(*) FROM user_context WHERE key LIKE 'learned_facts_%'").strip()
if mine not in ("0", ""):
    psql_file("DELETE FROM user_context WHERE key LIKE 'learned_facts_%';")
    print("  مفتاحي اليومي (learned_facts_*): اتمسح", mine)
    tot += int(mine or 0)
print("  الإجمالي اللي اتمسح:", tot, "صف")

print("\n" + "█" * 78)
print("█  ③ التغذية بالمعلومات الحقيقية")
print("█" * 78)
stmts = []
for k, v in REAL:
    stmts.append("INSERT INTO user_context (owner_id, key, value, updated_at) VALUES ('%s', '%s', '%s', now()) "
                 "ON CONFLICT (owner_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();"
                 % (owner, k, v.replace("'", "''")))
print(psql_file("\n".join(stmts))[:200])

print("\n" + "█" * 78)
print("█  ④ بعد التنضيف والتغذية")
print("█" * 78)
print("  صفوف user_context:", psql("SELECT count(*) FROM user_context").strip())
print("  عناصر memory_items:", psql("SELECT count(*) FROM memory_items").strip())
for p in FAKE:
    print("   وهمي «%s» → user_context=%s · memory_items=%s"
          % (p, psql("SELECT count(*) FROM user_context WHERE value ILIKE '%%%s%%'" % p).strip(),
             psql("SELECT count(*) FROM memory_items WHERE content ILIKE '%%%s%%'" % p).strip()))

print("\n  ── المعلومات الحقيقية اللي اتغذّت ──")
for line in psql("SELECT key || ' :: ' || left(value, 120) FROM user_context WHERE owner_id='%s' ORDER BY key" % owner).splitlines():
    if line.strip(): print("   ", line[:180])

print("\nDONE-FEED")
