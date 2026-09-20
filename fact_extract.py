#!/usr/bin/env python3
"""استخراج الحقايق من محادثات نبيل بموديلنا المحلي → ذاكرة أذكى.

الفكرة: بدل ما نخزّن المحادثة كاملة، الموديل يستخرج حقايق قصيرة ثابتة
(اسمه، شغله، تفضيلاته، مشاريعه) وتتخزّن كعناصر مستقلة تُسترجع بدقة.
"""
import http.client, json, re, socket, time, urllib.request

SOCK = "/var/run/docker.sock"


class U(http.client.HTTPConnection):
    def __init__(s, p): super().__init__("localhost"); s._p = p

    def connect(s):
        sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sk.settimeout(600); sk.connect(s._p); s.sock = sk


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


cs = dk("GET", "/containers/json")
def find(sub):
    for c in (cs or []):
        if sub in " ".join(c.get("Names") or []):
            return c
    return None


# --- المفتاح من حاوية الخدمة (بدون طبعه) ---
llm = find("grow-bench") if False else None
for c in (cs or []):
    if "-llm-" in " ".join(c.get("Names") or []):
        llm = c
        break
key = ""
if llm:
    info = dk("GET", "/containers/%s/json" % llm["Id"])
    for e in (((info or {}).get("Config") or {}).get("Env") or []):
        if e.startswith("LLM_API_KEY="):
            key = e.split("=", 1)[1]

pg = find("titan-titan-wqx9l7-postgres")
env = {}
if pg:
    txt = exec_in(pg["Id"], ["sh", "-c", "env | grep -E '^POSTGRES_(USER|DB|PASSWORD)=' | sed 's/^/export /'"])
    for line in txt.splitlines():
        m = re.match(r"export POSTGRES_(\w+)=(.*)", line.strip())
        if m:
            env[m.group(1)] = m.group(2).strip()


def psql(sql):
    q = "export PGPASSWORD='%s'; psql -U %s -d %s -tAc \"%s\"" % (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), sql)
    return exec_in(pg["Id"], ["sh", "-c", q])


def llm_call(prompt, max_tokens=220):
    rq = urllib.request.Request("http://llm:8080/v1/chat/completions",
                                data=json.dumps({"messages": [{"role": "user", "content": prompt}],
                                                 "max_tokens": max_tokens, "temperature": 0.1}).encode(),
                                headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    return json.load(urllib.request.urlopen(rq, timeout=300))["choices"][0]["message"]["content"].strip()


PROMPT = """استخرج الحقايق الثابتة عن المستخدم (نبيل) من المحادثة دي.

قواعد صارمة:
- كل حقيقة جملة عربية قصيرة واحدة، تبدأ بذكر صاحبها لو مش واضح.
- حقايق ثابتة فقط: الاسم، الشغل، العيلة، المشاريع، التفضيلات، القرارات.
- ممنوع: الآراء اللحظية، التفاصيل المؤقتة، كلام المساعد عن نفسه، أي شرح.
- لو مفيش حقايق ثابتة، رجّع: {"facts": []}

أرجع JSON فقط بدون أي كلام تاني:
{"facts": ["...", "..."]}

المحادثة:
%s"""

print("=== 1) بنقرا المحادثات ===")
raw = psql("SELECT coalesce(json_agg(json_build_object('id', external_id::text, 'cid', collection_id::text, "
           "'content', left(coalesce(content,''),1200))),'[]'::json) FROM memory_items "
           "WHERE external_id NOT LIKE '%:q' AND external_id NOT LIKE '%:a' AND external_id NOT LIKE '%:f%' LIMIT 30")
recs = []
try:
    recs = json.loads(raw.strip().splitlines()[-1])
except Exception as e:
    print("  ⚠️", str(e)[:100])
print("  عدد المحادثات: %d · مفتاح الخدمة: %s" % (len(recs), "موجود" if key else "مفقود"))

print("\n=== 2) بنستخرج الحقايق بموديلنا ===")
sqls, facts_total, done, failed = [], 0, 0, 0
import hashlib
for i, r in enumerate(recs, 1):
    txt = " ".join((r.get("content") or "").split())[:900]
    if not txt:
        continue
    try:
        out = llm_call(PROMPT % txt, 220)
        m = re.search(r"\{.*\}", out, re.S)
        data = json.loads(m.group(0)) if m else {"facts": []}
        facts = [str(f).strip() for f in (data.get("facts") or []) if str(f).strip()]
        for f in facts:
            if len(f) < 8 or len(f) > 200:
                continue
            fid = "fact:" + hashlib.sha1(f.encode("utf-8")).hexdigest()[:16]
            sqls.append((fid, r.get("cid"), f))
        facts_total += len(facts)
        done += 1
        print("  [%d/%d] حقايق: %d  →  %s" % (i, len(recs), len(facts), " · ".join(f[:60] for f in facts[:3])[:150]))
    except Exception as e:
        failed += 1
        print("  [%d/%d] ❌ %s" % (i, len(recs), str(e)[:80]))
print("\n  ✅ محادثات: %d · حقايق: %d · فشل: %d" % (done, facts_total, failed))

print("\n=== 3) بنخزّن الحقايق (بتمثيل) ===")
stored = 0
if sqls:
    lines = []
    for fid, cid, f in sqls:
        try:
            rq = urllib.request.Request("https://embed.orcanox.xyz/v1/embeddings",
                                        data=json.dumps({"input": f}).encode("utf-8"),
                                        headers={"Content-Type": "application/json"})
            v = json.load(urllib.request.urlopen(rq, timeout=60))["data"][0]["embedding"]
            lit = "[" + ",".join("%.6f" % x for x in v) + "]"
            lines.append("INSERT INTO memory_items (collection_id, external_id, content, embedding_vec, metadata, updated_at) "
                         "VALUES ('%s','%s','%s','%s'::vector,'{\"derived\":\"fact\"}'::jsonb, now()) ON CONFLICT DO NOTHING;"
                         % (cid, fid, f.replace("'", "''"), lit))
            stored += 1
        except Exception:
            pass
    if lines:
        import io, tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            data = "\n".join(lines).encode("utf-8")
            ti = tarfile.TarInfo(name="facts.sql"); ti.size = len(data); ti.mode = 0o644
            tf.addfile(ti, io.BytesIO(data))
        buf.seek(0)
        c = U(SOCK)
        c.request("PUT", "/containers/%s/archive?path=/tmp" % pg["Id"], body=buf.read(),
                  headers={"Content-Type": "application/x-tar"})
        c.getresponse().read(); c.close()
        out = exec_in(pg["Id"], ["sh", "-c", "export PGPASSWORD='%s'; psql -U %s -d %s -q -f /tmp/facts.sql 2>&1 | tail -2; "
                                            "psql -U %s -d %s -tAc \"SELECT count(*) FROM memory_items\"" %
                                            (env.get("PASSWORD", ""), env.get("USER"), env.get("DB"), env.get("USER"), env.get("DB"))])
        print("  نتيجة:", out.replace("\n", " "))
print("  ✅ جاهز للتخزين: %d" % stored)

print("\n=== 4) اختبار: أسئلة عن الحقايق ===")
for q in ["اسم نبيل إيه؟", "نبيل بيشتغل فين؟", "إيه مشاريع نبيل؟"]:
    try:
        rq = urllib.request.Request("https://embed.orcanox.xyz/v1/embeddings",
                                    data=json.dumps({"input": q}).encode("utf-8"),
                                    headers={"Content-Type": "application/json"})
        qv = json.load(urllib.request.urlopen(rq, timeout=60))["data"][0]["embedding"]
        lit = "[" + ",".join("%.6f" % x for x in qv) + "]"
        res = psql("SELECT round((1-(embedding_vec <=> '%s'::vector))::numeric,3)||' | '||coalesce(left(content,80),'') "
                   "FROM memory_items WHERE embedding_vec IS NOT NULL ORDER BY embedding_vec <=> '%s'::vector LIMIT 3" % (lit, lit))
        print("\n  🔎 %s" % q)
        for line in res.splitlines():
            if line.strip():
                print("     ", line.strip())
    except Exception as e:
        print("  ❌", str(e)[:90])

print("\n=== 5) إجمالي العناصر ===")
print("  ", psql("SELECT count(*) FROM memory_items").strip())
print("\nDONE-FACT-EXTRACT")
