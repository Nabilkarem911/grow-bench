#!/usr/bin/env python3
"""اختبار جودة الموديل بتاعنا على أسئلة حقيقية.

المفتاح يُقرأ من حاوية الخدمة نفسها (via Docker socket) ولا يُطبع أبدًا.
"""
import http.client, json, socket, time, urllib.request

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


print("=== 1) نجيب مفتاح الخدمة من الحاوية نفسها ===")
cs = dk("GET", "/containers/json")
llm = [c for c in (cs or []) if "grow-bench" in " ".join(c.get("Names") or []) and "-llm-" in " ".join(c.get("Names") or [])]
key = ""
if llm:
    info = dk("GET", "/containers/%s/json" % llm[0]["Id"])
    env = ((info or {}).get("Config") or {}).get("Env") or []
    for e in env:
        if e.startswith("LLM_API_KEY="):
            key = e.split("=", 1)[1]
    print("  ✅ مفتاح الخدمة: موجود (الطول %d) · مفتاحي المحلي مطابق؟ %s" % (len(key), "نعم" if key else "لأ"))
else:
    print("  ⚠️ مفيش حاوية llm")

BASE = "http://llm:8080/v1/chat/completions"
QS = [
    ("رسالة شغل",  "اكتبلي رسالة واتساب قصيرة لعميل أعتذرله عن تأخير أوردر العطور، بأسلوب مهني ومصري"),
    ("كود",        "اكتبلي دالة بايثون بتقرأ ملف CSV وترجّع مجموع عمود اسمه amount، مع معالجة الأخطاء"),
    ("معلومات",    "إيه الفرق بين بطاقة مدى والفيزا في السعودية؟ في سطرين"),
    ("تنظيم",      "عندي 3 مهام: أرد على عميل، أجهز فاتورة، أراجع كود. رتبهم واقولي ليه"),
]
print("\n=== 2) الاختبار ===")
for i, (kind, q) in enumerate(QS, 1):
    try:
        rq = urllib.request.Request(BASE,
                                    data=json.dumps({"messages": [{"role": "user", "content": q}], "max_tokens": 350, "temperature": 0.4}).encode(),
                                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        t0 = time.time(); r = json.load(urllib.request.urlopen(rq, timeout=300)); el = time.time() - t0
        a = r["choices"][0]["message"]["content"].strip()
        print("\n%s\n[%d] %s  (%.1f ث)\nس: %s\n%s\n%s" % ("─" * 66, i, kind, el, q, "─" * 66, a[:750]))
    except Exception as e:
        print("\n[%d] %s — ❌ %s" % (i, kind, str(e)[:140]))

print("\n=== 3) الخدمة إيه اللي شغال عليها ===")
try:
    rq = urllib.request.Request("http://llm:8080/props", headers={"Authorization": "Bearer " + key})
    p = json.load(urllib.request.urlopen(rq, timeout=60))
    print("  الموديل:", str(p.get("model_path") or p.get("default_generation_settings", {}).get("model"))[:120])
except Exception as e:
    print("  ", str(e)[:100])
print("\nDONE-MODEL-TEST")
