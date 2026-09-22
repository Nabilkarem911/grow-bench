#!/usr/bin/env python3
"""
خدمة تيتان — النسخة اللي بتشتغل على السيرفر (لايف).

نفس منطق النسخة المحلية، بس شغالة 24 ساعة على السيرفر.
مش بتلمس أي حاجة تانية. المفاتيح كلها من env.

المسارات:
  /            صفحة بسيطة للاختبار من الموبايل
  /chat        POST {text}  ->  {reply, ...}
  /health      GET  ->  {ok:true}
"""
import json
import os
import time
import urllib.request
import urllib.error

PORT = int(os.environ.get("PORT", "8077"))

MIMO_KEY = os.environ.get("MIMO_DIRECT_KEY", "")
MIMO_URL = os.environ.get("MIMO_DIRECT_URL", "https://api.xiaomimimo.com/v1").rstrip("/") + "/chat/completions"
MIMO_MODEL = os.environ.get("MIMO_MODEL", "xiaomi/mimo-v2.6-flash")

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/") + "/chat/completions"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

FACTS_JSON = os.environ.get("TITAN_FACTS_JSON", "")

MAX_REPLY_TOKENS = 400
MAX_TASK_TOKENS = 800
TIMEOUT = 120

SYSTEM = """إنت مساعد شخصي اسمه تيتان، بتتكلم مصري طبيعي زي صاحبك.
قواعد صارمة:
- رد قصير ومباشر. مفيش مقدمات ولا كلام زيادة.
- المصري هو الأساس: «إزاي أساعدك؟» مش «كيف أساعدك».
- لو السؤال بسيط، رد في سطر أو اتنين.
- مفيش حشو. لو مش عارف، قول مش عارف."""

SIMPLE_WORDS = ["صباح", "مساء", "السلام عليكم", "شكرا", "تمام", "ازيك", "إزيك", "اخبارك",
                "أخبارك", "تصبح", "باي", "hello", "hi", "thanks", "ماشي", "طيب", "اوك",
                "أوك", "ok", "تحياتي", "ربنا يخليك", "اهلا", "أهلا", "هاي"]
TASK_VERBS = ["اكتب", "أكتب", "اعمل", "أعمل", "ابحث", "أبحث", "حلل", "صلح", "نفذ",
              "احسب", "لخص", "رتب", "جهز", "ابعت", "راجع", "ترجم", "اشرح", "قارن",
              "اختبر", "اقرا", "اقرأ", "open", "write", "search", "find", "fix", "build"]

FACTS_DEFAULT = {
    "name": "نبيل كريم",
    "city": "ينبع، السعودية",
    "workplace": "موظف في مؤسسة مطاعم عميد البحارة (موظف، مش المالك)",
    "wife": "سماح حمدي عبد المقصود النجار",
    "son": "كنان نبيل — مواليد 7/2022",
    "role": "مطور Full Stack",
    "age": "36 سنة",
    "style": "بيحب المصري في الكلام والأرقام بالبلدي — مش الفصحى",
}


def facts_text():
    facts = FACTS_DEFAULT
    if FACTS_JSON:
        try:
            facts = json.loads(FACTS_JSON)
        except Exception:
            pass
    keep = ["name", "city", "workplace", "company", "wife", "son", "role", "style", "age"]
    parts = ["%s: %s" % (k, facts[k]) for k in keep if k in facts]
    if not parts:
        return ""
    return chr(10) + "معلومات عن المستخدم (استخدمها لو ليها علاقة بالسؤال):" + chr(10) + chr(10).join(parts)


def post(url, body, headers, timeout=TIMEOUT):
    rq = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(rq, timeout=timeout))
    return r, round((time.time() - t0) * 1000)


def call_mimo(messages, max_tokens):
    r, ms = post(MIMO_URL, {"model": MIMO_MODEL, "messages": messages, "max_tokens": max_tokens},
                 {"Authorization": "Bearer " + MIMO_KEY})
    txt = (r.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    return txt.strip(), ms, (r.get("usage") or {}).get("total_tokens", 0)


def call_deepseek(messages, max_tokens):
    r, ms = post(DEEPSEEK_URL, {"model": DEEPSEEK_MODEL, "messages": messages,
                                "max_tokens": max_tokens, "temperature": 0.6},
                 {"Authorization": "Bearer " + DEEPSEEK_KEY})
    txt = (r.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    return txt.strip(), ms, (r.get("usage") or {}).get("total_tokens", 0)


def call_model(messages, max_tokens):
    if MIMO_KEY:
        try:
            txt, ms, toks = call_mimo(messages, max_tokens)
            if txt:
                return txt, ms, toks, "mimo"
        except Exception as e:
            print("[mimo fail -> deepseek]", str(e)[:100], flush=True)
    if DEEPSEEK_KEY:
        txt, ms, toks = call_deepseek(messages, max_tokens)
        return txt, ms, toks, "deepseek"
    return "مفيش مزود متاح", 0, 0, "none"


def classify(text):
    t = (text or "").strip()
    low = t.lower()
    if any(v in t for v in TASK_VERBS):
        return "task"
    if any(w in low for w in SIMPLE_WORDS) or len(t) < 25:
        return "simple"
    return "simple" if len(t) < 45 else "task"


def run(text):
    t0 = time.time()
    kind = classify(text)
    msgs = [{"role": "system", "content": SYSTEM + facts_text()},
            {"role": "user", "content": text}]
    max_tok = MAX_REPLY_TOKENS if kind == "simple" else MAX_TASK_TOKENS
    try:
        reply, model_ms, toks, provider = call_model(msgs, max_tok)
    except Exception as e:
        reply, model_ms, toks, provider = "حصلت مشكلة: " + str(e)[:150], 0, 0, "error"
    return {"input": text, "reply": reply, "path": kind, "steps": 1,
            "tokens": toks, "model_ms": model_ms, "provider": provider,
            "latency_ms": round((time.time() - t0) * 1000)}


PAGE = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>تيتان</title><style>
body{font-family:system-ui;margin:0;background:#0d1117;color:#e6edf3;padding:16px}
h2{margin:0 0 12px;font-size:18px}
#log{border:1px solid #30363d;border-radius:12px;padding:12px;height:60vh;overflow:auto;background:#161b22}
.msg{margin:8px 0;padding:8px 12px;border-radius:10px;max-width:85%;white-space:pre-wrap;line-height:1.6}
.me{background:#1f6feb;margin-left:auto}
.bot{background:#21262d}
.meta{font-size:11px;color:#8b949e;margin-top:4px}
#bar{display:flex;gap:8px;margin-top:12px}
input{flex:1;padding:12px;border-radius:10px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:16px}
button{padding:12px 18px;border-radius:10px;border:0;background:#238636;color:#fff;font-size:16px}
</style></head><body>
<h2>تيتان</h2>
<div id="log"></div>
<div id="bar"><input id="q" placeholder="اكتب رسالتك" autocomplete="off"><button onclick="go()">ابعت</button></div>
<script>
const log=document.getElementById('log'),q=document.getElementById('q');
function add(cls,txt,meta){const d=document.createElement('div');d.className='msg '+cls;d.textContent=txt;
 if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;d.appendChild(m);}
 log.appendChild(d);log.scrollTop=log.scrollHeight;}
async function go(){const t=q.value.trim();if(!t)return;q.value='';add('me',t);add('bot','...');
 try{const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
  const j=await r.json();log.lastChild.remove();
  add('bot',j.reply||'(فاضي)','الزمن '+j.latency_ms+' مللي | '+j.provider+' | '+j.tokens+' توكن');
 }catch(e){log.lastChild.remove();add('bot','خطأ: '+e);}}
q.addEventListener('keydown',e=>{if(e.key==='Enter')go()});
</script></body></html>"""


def main():
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            print("%s %s" % (self.address_string(), fmt % a), flush=True)

        def do_GET(self):
            if self.path == "/health":
                b = json.dumps({"ok": True, "mimo": bool(MIMO_KEY), "deepseek": bool(DEEPSEEK_KEY)}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            b = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_POST(self):
            if self.path != "/chat":
                self.send_response(404)
                self.end_headers()
                return
            n = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                body = {}
            out = run(body.get("text", ""))
            data = json.dumps(out, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    print("titan service on :%d (mimo=%s deepseek=%s)" % (PORT, bool(MIMO_KEY), bool(DEEPSEEK_KEY)), flush=True)
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
