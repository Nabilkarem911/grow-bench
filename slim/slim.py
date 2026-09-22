#!/usr/bin/env python3
"""
Titan Slim v0 — مسار سريع موازي. مش بيلمس تيتان ولا أي حاجة شغالة.

الفكرة (ببالدقي: خطوة واحدة للبسيط، و3 خطوات كحد أقصى للمهام):
  رسالة → تصنيف سريع (0.6 ث) → 
      بسيط  → نداء واحد → رد           (الهدف < 5 ثواني)
      مهمة  → 3 خطوات كحد أقصى          (الهدف < 30 ثانية)

الاستخدام:
  python slim.py                    # اختبار داخلي (3 رسايل)
  python slim.py "رسالتك"           # رسالة واحدة
  python slim.py --serve            # خدمة HTTP على 8077
"""
import json, os, re, sys, time, urllib.request

# ── الإعدادات (من env — مفيش أسرار في الكود) ──
def load_secrets():
    """مفاتيح إضافية من ملفات .secrets"""
    for f in ("/f/projects/billy/mimo/O.M.E.G.A/.secrets/mimo_direct.env",
              os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secrets", "mimo_direct.env")):
        if os.path.exists(f):
            for line in open(f, encoding="utf-8", errors="ignore"):
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v)
            return


def load_secrets():
    for f in ("/f/projects/billy/mimo/O.M.E.G.A/.secrets/mimo_direct.env",
              os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secrets", "mimo_direct.env")):
        if os.path.exists(f):
            for line in open(f, encoding="utf-8", errors="ignore"):
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v)
            return


def load_env():
    p = os.path.expanduser("~/AppData/Local/hermes/.env")
    if not os.path.exists(p): return
    for line in open(p, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()
load_secrets()

# نتأكد إن مفتاح شاومي اتقرا
if not os.environ.get("MIMO_DIRECT_KEY"):
    for _f in ("/f/projects/billy/mimo/O.M.E.G.A/.secrets/mimo_direct.env",):
        if os.path.exists(_f):
            for _l in open(_f, encoding="utf-8", errors="ignore"):
                if _l.startswith("MIMO_DIRECT_KEY="):
                    os.environ["MIMO_DIRECT_KEY"] = _l.split("=", 1)[1].strip()

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MS_KEY = os.environ.get("MILLISECONDS_API_KEY", "")
MS_URL = "https://api.milliseconds.ai/v1/decision-machine-1/yes-no"

FACTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facts.json")

SIMPLE_MODEL = "deepseek-chat"

MAX_TASK_STEPS = 3
MAX_REPLY_TOKENS = 400

# مزود شاومي المجاني (مباشر — البروكسي المحلي بتاعهم بيرجّع 502)
MIMO_KEY = os.environ.get("MIMO_DIRECT_KEY", "")
MIMO_URL = os.environ.get("MIMO_DIRECT_URL", "https://api.xiaomimimo.com/v1") + "/chat/completions"
MIMO_MODEL = "xiaomi/mimo-v2.6-flash"


def call_mimo(messages, max_tokens=MAX_REPLY_TOKENS):
    r, ms = post(MIMO_URL, {"model": MIMO_MODEL, "messages": messages, "max_tokens": max_tokens},
                 {"Authorization": "Bearer " + MIMO_KEY}, timeout=120)
    txt = (r.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    toks = (r.get("usage") or {}).get("total_tokens", 0)
    return txt.strip(), ms, toks


def post(url, body, headers, timeout=60):
    rq = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                headers={"Content-Type": "application/json", **headers})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(rq, timeout=timeout))
    return r, round((time.time() - t0) * 1000)


# ── التصنيف محلي (0 مللي — مقاس: milliseconds.ai اتأخر 21-36 ثانية ✗) ──
SIMPLE_WORDS = ["صباح", "مساء", "السلام عليكم", "شكرا", "تمام", "ازيك", "إزيك", "اخبارك",
                "أخبارك", "ها يا", "تصبح", "باي", "hello", "hi", "thanks", "يسلمو", "جميل",
                "ماشي", "طيب", "اوك", "أوك", "ok", "تحياتي", "ربنا يخليك"]
TASK_VERBS = ["اكتب", "أكتب", "اعمل", "أعمل", "ابحث", "أبحث", "حلل", "صلح", "نفذ",
              "احسب", "لخص", "رتب", "جهز", "ابعت", "راجع", "ترجم", "اشرح", "قارن",
              "اختبر", "اقرا", "اقرأ", "open", "write", "search", "find", "fix", "build"]


def classify(text):
    """تصنيف محلي فوري — كود مش موديل (المهام المنظمة القواعد بتغلب الموديل فيها)."""
    t = (text or "").strip()
    low = t.lower()
    if any(v in t for v in TASK_VERBS):
        return "task", 0, 1.0
    if any(w in low for w in SIMPLE_WORDS) or len(t) < 25:
        return "simple", 0, 0.9
    return "simple" if len(t) < 45 else "task", 0, 0.7


def call_model(messages, max_tokens=MAX_REPLY_TOKENS):
    r, ms = post(DEEPSEEK_URL, {
        "model": SIMPLE_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }, {"Authorization": "Bearer " + DEEPSEEK_KEY}, timeout=120)
    txt = (r.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    toks = (r.get("usage") or {}).get("total_tokens", 0)
    return txt.strip(), ms, toks


SYSTEM = """إنت مساعد شخصي اسمه تيتان، بتتكلم مصري طبيعي زي صاحبك.
قواعد صارمة:
- رد قصير ومباشر. مفيش مقدمات ولا «أهلاً بك» ولا «كيف يمكنني مساعدتك».
- المصري هو الأساس: «إزاي أساعدك؟» مش «كيف أساعدك».
- لو السؤال بسيط، رد في سطر أو اتنين. متطولش.
- مفيش حشو ولا كلام زيادة. لو مش عارف، قول مش عارف."""


def load_facts():
    """حقايق المستخدم — نفس اللي في تيتان (نحفظها محليًا عشان تكون فورية)."""
    if not os.path.exists(FACTS_FILE):
        return {}
    try:
        return json.load(open(FACTS_FILE, encoding="utf-8"))
    except Exception:
        return {}


def facts_line():
    f = load_facts()
    if not f:
        return ""
    keep = ["name", "city", "workplace", "company", "wife", "son", "role", "style", "age"]
    parts = ["%s: %s" % (k, f[k]) for k in keep if k in f]
    if not parts:
        parts = ["%s: %s" % (k, v) for k, v in list(f.items())[:10]]
    head = "معلومات عن المستخدم (استخدمها لو ليها علاقة بالسؤال):"
    return chr(10) + head + chr(10) + (chr(10).join(parts))

def run(text, verbose=True):
    T0 = time.time()
    result = {"input": text, "path": None, "reply": "", "steps": 0,
              "tokens": 0, "latency_ms": 0, "breakdown": {}}

    kind, cms, prob = classify(text)
    result["path"] = kind
    result["breakdown"]["classify_ms"] = cms

    if kind == "simple":
        # ⚡ المسار السريع: نداء واحد بس
        msgs = [{"role": "system", "content": SYSTEM + facts_line()},
                {"role": "user", "content": text}]
        used = "mimo"
        if MIMO_KEY:
            try:
                reply, mms, toks = call_mimo(msgs)
            except Exception as e:
                print("  [شاومي فشل → بنرجع لDeepSeek]", str(e)[:60])
                reply, mms, toks = call_model(msgs); used = "deepseek"
        else:
            reply, mms, toks = call_model(msgs); used = "deepseek"
        result["breakdown"]["provider"] = used
        result.update(reply=reply, steps=1, tokens=toks)
        result["breakdown"]["model_ms"] = mms
    else:
        # مهمة: 3 خطوات كحد أقصى (هنا خطوة واحدة في v0 — التوسيع في v1)
        reply, mms, toks = call_model([
            {"role": "system", "content": SYSTEM + "\nالمستخدم طلب مهمة — نفّذها مباشرة ورد بالنتيجة."},
            {"role": "user", "content": text},
        ], max_tokens=800)
        result.update(reply=reply, steps=1, tokens=toks)
        result["breakdown"]["model_ms"] = mms

    result["latency_ms"] = round((time.time() - T0) * 1000)
    if verbose:
        print("\n" + "─" * 60)
        print("السؤال:", text[:90])
        print("المسار:", "⚡ سريع" if kind == "simple" else "🧠 مهمة", "(ثقة %.2f)" % prob)
        print("الزمن:", "%.2f ثانية" % (result["latency_ms"] / 1000),
              "│ تصنيف %d مللي │ موديل %d مللي" % (cms, result["breakdown"].get("model_ms", 0)))
        print("الخطوات: %d │ التوكنات: %d" % (result["steps"], result["tokens"]))
        print("الرد:", reply[:250])
    return result




PAGE = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Titan Slim</title><style>
body{font-family:system-ui;margin:0;background:#0d1117;color:#e6edf3;padding:16px}
h2{margin:0 0 12px;font-size:18px}
#log{border:1px solid #30363d;border-radius:12px;padding:12px;height:58vh;overflow:auto;background:#161b22}
.msg{margin:8px 0;padding:8px 12px;border-radius:10px;max-width:85%;white-space:pre-wrap}
.me{background:#1f6feb;margin-left:auto}
.bot{background:#21262d}
.meta{font-size:11px;color:#8b949e;margin-top:4px}
#bar{display:flex;gap:8px;margin-top:12px}
input{flex:1;padding:12px;border-radius:10px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:16px}
button{padding:12px 18px;border-radius:10px;border:0;background:#238636;color:#fff;font-size:16px}
</style></head><body>
<h2>Titan Slim — جرّبني</h2>
<div id="log"></div>
<div id="bar"><input id="q" placeholder="اكتب رسالتك..." autocomplete="off"><button onclick="go()">ابعت</button></div>
<script>
const log=document.getElementById('log'),q=document.getElementById('q');
function add(cls,txt,meta){const d=document.createElement('div');d.className='msg '+cls;d.textContent=txt;
 if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;d.appendChild(m);}
 log.appendChild(d);log.scrollTop=log.scrollHeight;}
async function go(){const t=q.value.trim();if(!t)return;q.value='';add('me',t);
 const t0=Date.now();add('bot','...');
 try{const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
  const j=await r.json();log.lastChild.remove();
  add('bot',j.reply||'(فاضي)','الزمن '+(Date.now()-t0)+' مللي · '+j.steps+' خطوة · '+j.tokens+' توكن · مسار '+j.path);
 }catch(e){log.lastChild.remove();add('bot','خطأ: '+e);}}
q.addEventListener('keydown',e=>{if(e.key==='Enter')go()});
</script></body></html>"""


def serve(port=8077):
    """خدمة HTTP بسيطة — للمقارنة مع تيتان."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            out = run(body.get("text", ""), verbose=False)
            data = json.dumps(out, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                b = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            d = b'{"ok":true,"service":"titan-slim-v0"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(d)))
            self.end_headers()
            self.wfile.write(d)

    print("Titan Slim v0 شغال على http://127.0.0.1:%d" % port)
    HTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    if not DEEPSEEK_KEY:
        print("❌ مفيش DEEPSEEK_API_KEY"); sys.exit(1)
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        serve()
    elif len(sys.argv) > 1:
        run(" ".join(sys.argv[1:]))
    else:
        print("═" * 60)
        print("Titan Slim v0 — مقارنة مع تيتان على نفس الرسايل")
        print("═" * 60)
        for m in ["صباح الخير", "اسمي ايه واشتغل فين؟", "ابحثلي عن أسعار العطور في السعودية"]:
            run(m)
        print("\n" + "═" * 60)
        print("للمقارنة — تيتان الحالي:")
        print("  صباح الخير   → 3 خطوات · 63 ثانية ✗")
        print("  اسمي ايه     → 1 خطوة · 18 ثانية")
        print("  أسعار العطور → 4 خطوات · 90 ثانية ✗")
