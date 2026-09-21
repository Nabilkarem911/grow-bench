#!/usr/bin/env python3
"""فحص ناقد شامل لتيتان — قراءة فقط، بلا أي تعديل."""
import http.client, json, re, socket

SOCK = "/var/run/docker.sock"


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p

    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(120); sk.connect(s._p); s.sock = sk


def dk(m, p, b=None, raw=False):
    c = U(SOCK)
    c.request(m, p, body=json.dumps(b).encode() if b is not None else None,
              headers={"Content-Type": "application/json"} if b else {})
    r = c.getresponse(); data = r.read(); c.close()
    if raw:
        return data
    try:
        return json.loads(data.decode("utf-8", "ignore"))
    except Exception:
        return data.decode("utf-8", "ignore")


def exec_in(cid, cmd, wd="/"):
    ex = dk("POST", "/containers/%s/exec" % cid,
            {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": False, "WorkingDir": wd})
    eid = (ex or {}).get("Id")
    if not eid:
        return "(فشل exec)"
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


def logs_of(cid, tail=120):
    raw = dk("GET", "/containers/%s/logs?stdout=1&stderr=1&tail=%d" % (cid, tail), raw=True)
    out, i = [], 0
    while i + 8 <= len(raw):
        n = int.from_bytes(raw[i + 4:i + 8], "big")
        if n > len(raw) - i - 8:
            break
        out.append(raw[i + 8:i + 8 + n].decode("utf-8", "ignore")); i += 8 + n
    return "".join(out) if out else raw.decode("utf-8", "ignore")


CS = dk("GET", "/containers/json")
def find(sub):
    for c in (CS or []):
        if sub in " ".join(c.get("Names") or []):
            return c
    return None


T = {}
print("╔" + "═" * 74 + "╗")
print("║  فحص تيتان الشامل — قراءة فقط" + " " * 43 + "║")
print("╚" + "═" * 74 + "╝")

# ── 1) الحاويات ──
print("\n【1】 الحاويات والحالة")
for c in (CS or []):
    nm = (c.get("Names") or [""])[0].lstrip("/")
    if "titan" in nm:
        st = str(c.get("State"))
        stt = str(c.get("Status"))
        mark = "✅" if st == "running" and "healthy" in stt else ("⚠️" if st == "running" else "❌")
        print("   %s %-44s %s" % (mark, nm[:44], stt[:30]))
        T[nm] = c

pg = find("titan-titan-wqx9l7-postgres")
rd = find("titan-titan-wqx9l7-redis")
core = find("titan-titan-wqx9l7-core-1")
wrk = find("titan-titan-wqx9l7-worker-1")

# ── 2) Redis ──
print("\n【2】 Redis (الكاش والطوابير)")
if rd:
    print("   " + (exec_in(rd["Id"], ["sh", "-c", "redis-cli -a \"$REDIS_PASSWORD\" ping 2>/dev/null || redis-cli ping 2>/dev/null || echo فشل"]).replace("\n", " ") or "?"))
    print("   الذاكرة:", exec_in(rd["Id"], ["sh", "-c", "redis-cli -a \"$REDIS_PASSWORD\" info memory 2>/dev/null | grep used_memory_human || redis-cli info memory 2>/dev/null | grep used_memory_human"]).strip()[:80])
    print("   مفاتيح:", exec_in(rd["Id"], ["sh", "-c", "redis-cli -a \"$REDIS_PASSWORD\" dbsize 2>/dev/null || redis-cli dbsize"]).strip()[:40])

# ── 3) Postgres ──
env = {}
if pg:
    for line in exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"]).splitlines():
        m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
        if m:
            env[m.group(1)] = m.group(2).strip()


def psql(sql):
    return exec_in(pg["Id"], ["sh", "-c", "export PGPASSWORD='%s'; psql -U %s -d %s -tAc \"%s\""
                              % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)])


print("\n【3】 قاعدة البيانات")
print("   الاتصالات النشطة:", psql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()").strip())
print("   حجم القاعدة:", psql("SELECT pg_size_pretty(pg_database_size(current_database()))").strip())
print("   أكبر 3 جداول:", psql("SELECT string_agg(relname||' ('||pg_size_pretty(pg_total_relation_size(relid))||')', ', ') FROM (SELECT relname, relid FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 3) t").strip()[:150])
print("   اتصالات مفتوحة طويلة (>5 دقايق):", psql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND now()-query_start > interval '5 minutes'").strip())

# ── 4) الـAPI ──
print("\n【4】 واجهة تيتان (API)")
if core:
    print("   " + exec_in(core["Id"], ["sh", "-c", "wget -qO- --timeout=10 http://localhost:3000/health 2>/dev/null || curl -s -m 10 http://localhost:3000/health 2>/dev/null || echo '(مفيش /health)'"]).strip()[:200])
    print("   " + exec_in(core["Id"], ["sh", "-c", "curl -s -m 10 http://localhost:3000/api/health 2>/dev/null || echo '(مفيش /api/health)'"]).strip()[:200])

# ── 5) اللوجات: أخطاء ──
print("\n【5】 اللوجات (آخر 120 سطر — بنحسب الأخطاء)")
for label, c in (("core", core), ("worker", wrk)):
    if not c:
        continue
    lg = logs_of(c["Id"], 120)
    errs = [l for l in lg.splitlines() if re.search(r"error|fail|exception|timeout|refused|fatal", l, re.I)]
    print("   %s: %d سطر · %d فيهم خطأ" % (label, len(lg.splitlines()), len(errs)))
    for e in errs[-4:]:
        print("      ⚠️ " + e.strip()[:150])

# ── 6) حالة التشغيل ──
print("\n【6】 الرسايل: حالة + أداء")
print("   التوزيع:", " · ".join(l.strip() for l in psql("SELECT status||'='||count(*) FROM agent_runs GROUP BY status ORDER BY count(*) DESC").splitlines() if l.strip()))
print("   معلقة (running أقدم من 10 دقايق):", psql("SELECT count(*) FROM agent_runs WHERE status IN ('running','pending') AND created_at < now() - interval '10 minutes'").strip())
print("   فاشلة آخر 24 ساعة:", psql("SELECT count(*) FROM agent_runs WHERE status NOT IN ('completed') AND created_at > now() - interval '24 hours'").strip())
print("\n   آخر 10 رسايل (وقت | توكن | خطوات | حالة):")
print("   " + " | ".join(l.strip() for l in psql("SELECT to_char(created_at,'HH24:MI')||' '||tokens_used||'t '||current_step||'s '||status FROM agent_runs WHERE tokens_used>0 ORDER BY created_at DESC LIMIT 10").splitlines()))
print("\n   إحصاء:", psql("SELECT 'المتوسط '||round(avg(tokens_used))||' · الوسيط '||round(percentile_cont(0.5) WITHIN GROUP (ORDER BY tokens_used))||' · أقصى '||max(tokens_used)||' · عينة '||count(*) FROM agent_runs WHERE tokens_used>0 AND created_at > now() - interval '24 hours'").strip())
print("   قبل التحويل:", psql("SELECT 'المتوسط '||round(avg(tokens_used))||' · الوسيط '||round(percentile_cont(0.5) WITHIN GROUP (ORDER BY tokens_used))||' · عينة '||count(*) FROM agent_runs WHERE tokens_used>0 AND created_at < now() - interval '24 hours'").strip())

# ── 7) جودة الردود ──
print("\n【7】 جودة الردود (آخر 40 رد)")
print("   صيني/كوري/روسي:", psql("SELECT count(*) FROM (SELECT content FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 40) t WHERE content ~ '[\\u4e00-\\u9fff\\uac00-\\ud7af\\u0400-\\u04ff]'").strip())
print("   ردود فاضية:", psql("SELECT count(*) FROM (SELECT content FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 40) t WHERE length(trim(content)) < 3").strip())
print("   تسريب إعدادات (ds_safety/</system):", psql("SELECT count(*) FROM (SELECT content FROM memory_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 40) t WHERE content ILIKE '%ds_safety%' OR content ILIKE '%</system%' OR content ILIKE '%<|%'").strip())
print("   رسائل مكررة (نفس الوقت):", psql("SELECT coalesce(sum(n-1),0)::text FROM (SELECT count(*) AS n FROM memory_messages GROUP BY session_id, role, content HAVING count(*)>1) t").strip())

# ── 8) الذاكرة ──
print("\n【8】 الذاكرة")
print("   العناصر:", psql("SELECT count(*) FROM memory_items").strip(), "· فيهم تمثيل:", psql("SELECT count(*) FROM memory_items WHERE embedding_vec IS NOT NULL").strip())
print("   التوزيع:", " · ".join(l.strip() for l in psql("SELECT coalesce(metadata->>'derived','turn')||'='||count(*) FROM memory_items GROUP BY 1 ORDER BY 2 DESC").splitlines() if l.strip()))
print("   عناصر بلا تمثيل:", psql("SELECT count(*) FROM memory_items WHERE embedding_vec IS NULL").strip())
print("   رسايل محفوظة:", psql("SELECT count(*) FROM memory_messages").strip(), "· جلسات:", psql("SELECT count(*) FROM sessions").strip())

# ── 9) الأدوات ──
print("\n【9】 الأدوات")
print("   إحصاءات التنفيذ:", psql("SELECT string_agg(tool_name||'='||calls, ', ') FROM (SELECT * FROM tool_execution_stats LIMIT 10) t").strip()[:200] or "(فاضي)")

# ── 10) تليجرام ──
print("\n【10】 تليجرام")
tok = ""
for c in (CS or []):
    nm = " ".join(c.get("Names") or [])
    if "titan" in nm or "grow" in nm:
        info = dk("GET", "/containers/%s/json" % c["Id"])
        for e in (((info or {}).get("Config") or {}).get("Env") or []):
            if e.startswith("TELEGRAM_BOT_TOKEN=") and not e.endswith("="):
                tok = e.split("=", 1)[1]
        if tok:
            break
if tok:
    print("   مندوب البوت موجود ✓ (الطول %d)" % len(tok))
    try:
        import urllib.request
        d = json.load(urllib.request.urlopen("https://api.telegram.org/bot%s/getWebhookInfo" % tok, timeout=30))
        r = d.get("result") or {}
        print("   الويبهوك:", str(r.get("url"))[:60] or "(مفيش)")
        print("   آخر خطأ:", str(r.get("last_error_message"))[:100] or "مفيش ✓")
    except Exception as e:
        print("   تعذّر الاستعلام:", str(e)[:70])
else:
    print("   ⚠️ مفيش توكن")

print("\nDONE-FULL-AUDIT")
