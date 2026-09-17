#!/usr/bin/env python3
"""capability_arena.py — بطولة «مين الأفضل في إيه» بمقاييس موضوعية.

كل موديل بياخد نفس الاختبارات، والتصحيح **آلي** (مش إحساس):
  • كود: بنستخرج الكود ونشغّله على حالات اختبار حقيقية
  • JSON: بنحلله ونتحقق من المفاتيح برمجيًا
  • حساب: بنتحقق من الرقم النهائي
  • عربي: بنحفظ النص للمراجعة البشرية (والسرعة بتتقاس)

النتيجة: /data/results/capability_arena.json
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, "/app")
try:
    import arena as A
except Exception:
    A = None

R = "/data/results"
MOE = "/data/moe"
LLAMA = "/data/llama"
PORT = 8097

MODELS = [
    ("Qwen2.5-Coder-1.5B", "https://huggingface.co/bartowski/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf", f"{MOE}/Qwen2.5-Coder-1.5B-Q4_K_M.gguf"),
    ("Yi-Coder-1.5B-Chat", "https://huggingface.co/bartowski/Yi-Coder-1.5B-Chat-GGUF/resolve/main/Yi-Coder-1.5B-Chat-Q4_K_M.gguf", f"{MOE}/Yi-Coder-1.5B-Q4_K_M.gguf"),
    ("Arabic-Qwen2.5-3B", "https://huggingface.co/mradermacher/Arabic-Qwen2.5-3B-GGUF/resolve/main/Arabic-Qwen2.5-3B.Q4_K_M.gguf", f"{MOE}/Arabic-Qwen2.5-3B-Q4_K_M.gguf"),
    ("MiniCPM5-1B", "https://huggingface.co/openbmb/MiniCPM5-1B-GGUF/resolve/main/MiniCPM5-1B-Q4_K_M.gguf", f"{MOE}/MiniCPM5-1B-Q4_K_M.gguf"),
    ("SmolLM3-3B", "https://huggingface.co/ggml-org/SmolLM3-3B-GGUF/resolve/main/SmolLM3-Q4_K_M.gguf", f"{MOE}/SmolLM3-3B-Q4_K_M.gguf"),
    ("LFM2.5-1.2B", None, f"{MOE}/LFM2.5-1.2B-Q4_K_M.gguf"),
    ("Qwen3-1.7B", None, f"{MOE}/Qwen3-1.7B-Q4_K_M.gguf"),
    ("ERNIE-4.5-21B-A3B", None, f"{MOE}/ERNIE-4.5-21B-A3B-Q4_K_M.gguf"),
]

# ── الاختبارات + التصحيح الآلي ─────────────────────────────────────────
CODE_IS_PRIME = """اكتب دالة بايثون اسمها `is_prime` بتاخد رقم وتُرجع True لو أولي و False لو مش أولي.
اكتب الكود في بلوك ```python فقط، من غير أي شرح."""

CODE_BUGFIX = """الدالة دي فيها باج:
```python
def sum_positive(nums):
    total = 0
    for n in nums:
        if n > 0:
            total = n
    return total
```
صلّحها بحيث تجمع كل الأرقام الموجبة. اكتب الكود المصلّح في بلوك ```python فقط."""

CODE_SQL = """عندك جدولين: customers(id, name) و orders(id, customer_id, total, created_at).
اكتب استعلام SQL واحد يجيب أسماء العملاء ومجموع مشترياتهم، للعملاء اللي مجموعهم أكبر من 1000، مرتب بالأعلى أولاً.
اكتب الـSQL في بلوك ```sql فقط."""

JSON_CLASSIFY = """صنّف الرسالة دي ورجّع **JSON فقط** (بدون أي كلام قبله أو بعده) بالمفاتيح بالظبط: type و urgency.
type يكون واحد من: complaint | request | greeting
urgency يكون واحد من: high | low
الرسالة: «فيه تأخير كبير في أوردري ومحتاج حل بسرعة»"""

JSON_TOOL = """رجّع **JSON فقط** (بدون كلام) يمثل نداء أداة بالشكل ده بالظبط:
{"name": "<اسم الأداة>", "arguments": {"<مفتاح>": "<قيمة>"}}
المطلوب: إرسال رسالة واتساب لعميل رقمه 966501234567 نصها «طلبك في الطريق».
استخدم اسم الأداة send_whatsapp."""

MATH = """عندي 3 صناديق: الأول فيه 5 تفاحات، والتاني ضعف الأول، والتالت فيه نصف مجموع الأول والتاني.
كام تفاحة الإجمالي؟ اكتب الرقم النهائي في آخر سطر بالشكل: الإجابة = <رقم>"""

ARABIC_COMPLAINT = """عميل بيقول: «فيه تأخير كبير في أوردري ومحتاج حل بسرعة».
اكتبلي رد مهني قصير على الرسالة دي، بالعربي، من غير أي مقدمات."""

ARABIC_SIMPLE = """اشرح لمزارع بسيط (بالعربي العامي) يعني إيه «الذكاء الاصطناعي» في 3 سطور، من غير مصطلحات."""


def run_code(code, tests, func_name):
    """يشغّل الكود فعليًا ويتحقق من النتائج — تصحيح موضوعي."""
    ns = {}
    try:
        exec(code, ns)
    except Exception as e:
        return 0.0, f"فشل التنفيذ: {str(e)[:80]}"
    fn = ns.get(func_name)
    if not callable(fn):
        return 0.0, f"مفيش دالة {func_name}"
    ok = 0
    for args, exp in tests:
        try:
            got = fn(*args)
            if got == exp:
                ok += 1
        except Exception:
            pass
    return ok / len(tests), f"{ok}/{len(tests)} حالة نجحت"


def extract(text, lang="python"):
    m = re.search(rf"```{lang}\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.*?)```", text, re.S)
    return m.group(1).strip() if m else text.strip()


def json_only(text):
    """يحاول يلقط JSON نضيف — ويرجّع (هل كان نضيف أصلاً، القيمة)."""
    t = text.strip()
    clean = t.startswith("{") and t.endswith("}")
    try:
        return clean, json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            return clean, json.loads(m.group(0))
        except Exception:
            return clean, None
    return clean, None


def score_test(title, text):
    """يرجّع (درجة 0-1, تفاصيل)"""
    if title.startswith("كود: is_prime"):
        code = extract(text)
        tests = [((2,), True), ((3,), True), ((4,), False), ((17,), True), ((1,), False), ((97,), True), ((100,), False)]
        return run_code(code, tests, "is_prime")
    if title.startswith("كود: إصلاح"):
        code = extract(text)
        tests = [(([1, -2, 3, -4, 5],), 9), (([-1, -2],), 0), (([0, 7],), 7)]
        return run_code(code, tests, "sum_positive")
    if title.startswith("SQL"):
        t = text.lower()
        s = 0.0
        if "join" in t: s += 0.35
        if "group by" in t: s += 0.2
        if "sum(" in t: s += 0.2
        if "having" in t: s += 0.2
        if "order by" in t and "desc" in t: s += 0.05
        return min(s, 1.0), f"عناصر صحيحة: {s:.2f}"
    if title.startswith("JSON: تصنيف"):
        clean, v = json_only(text)
        if not isinstance(v, dict): return 0.0, "JSON فاشل"
        pts = (0.3 if clean else 0.0)
        if v.get("type") in ("complaint",): pts += 0.4
        if v.get("urgency") in ("high",): pts += 0.3
        return min(pts, 1.0), f"نضيف={clean} · {json.dumps(v, ensure_ascii=False)[:70]}"
    if title.startswith("JSON: أداة"):
        clean, v = json_only(text)
        if not isinstance(v, dict): return 0.0, "JSON فاشل"
        pts = (0.3 if clean else 0.0)
        if v.get("name") == "send_whatsapp": pts += 0.35
        a = v.get("arguments") or {}
        if isinstance(a, dict) and ("966501234567" in json.dumps(a)): pts += 0.35
        return min(pts, 1.0), f"نضيف={clean} · {json.dumps(v, ensure_ascii=False)[:90]}"
    if title.startswith("حساب"):
        # ‏ملاحظة: كان المدقّق بيرفض إجابات صحيحة لما الموديل يكتب 22.5 جوه صيغة رياضية
        # (زي \text{الإجابة} = 5 + 10 + 7.5 = 22.5) — فبنقبل أي ذكر للرقم الصح.
        t = text.replace("٢٢.٥", "22.5").replace("٢٢,٥", "22.5")
        if re.search(r"22[.,]5", t):
            return 1.0, "22.5 ✔"
        nums = re.findall(r"\d+[.,]?\d*", t)
        if nums:
            return 0.0, f"إجابة غلط (آخر رقم: {nums[-1]})"
        return 0.0, "مفيش إجابة رقمية"
    return None, ""  # اختبارات بشرية


TESTS = [("كود: is_prime", CODE_IS_PRIME), ("كود: إصلاح", CODE_BUGFIX), ("SQL: استعلام", CODE_SQL),
         ("JSON: تصنيف", JSON_CLASSIFY), ("JSON: أداة", JSON_TOOL), ("حساب", MATH),
         ("عربي: رد على شكوى", ARABIC_COMPLAINT), ("عربي: تبسيط", ARABIC_SIMPLE)]


def save(rep):
    os.makedirs(R, exist_ok=True)
    with open(f"{R}/capability_arena.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)


def main():
    sys.argv = ["arena"]  # نستفيد من دوال arena
    A.PORT = PORT         # ⚠️ مهم: نوحّد الباب — وإلا الانتظار يقف على باب غلط
    srv = A.find_bin("llama-server")
    ld = os.path.dirname(srv)
    A.sh("apt-get update -qq && apt-get install -y -qq libgomp1 libstdc++6 procps >/dev/null 2>&1", timeout=600)

    rep = {"when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "tests": [t[0] for t in TESTS], "models": {}}
    save(rep)

    for name, url, path in MODELS:
        e = {"tests": {}}
        ok, note = A.ensure(path, url)
        e["download"] = note
        if not ok:
            e["error"] = note; rep["models"][name] = e; save(rep); continue
        e["size_gb"] = round(os.path.getsize(path) / 2**30, 2)
        print(f"\n===== {name} ({e['size_gb']}ج) =====", flush=True)

        A.kill_servers()
        cmd = (f'LD_LIBRARY_PATH="{ld}:{LLAMA}:$LD_LIBRARY_PATH" "{srv}" -m "{path}" -ngl 0 -t 3 '
               f'-c 2048 -nr -rea off --repeat-penalty 1.15 --no-warmup --host 127.0.0.1 --port {PORT}')
        logp = f"{R}/cap_srv_{name}.log"
        log = open(logp, "w")
        proc = subprocess.Popen(cmd, shell=True, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        load = A.wait_ready()
        e["load_s"] = round(load, 1) if load else None
        if load is None:
            e["error"] = "الخادم ماقامش"
            try:
                e["log"] = open(logp, encoding="utf-8", errors="replace").read()[-400:]
            except Exception:
                pass
            A.kill_servers(); rep["models"][name] = e; save(rep); continue

        # تحقق الهوية
        try:
            props = A.api("/props", timeout=30) if hasattr(A, "api") else None
        except Exception:
            props = None
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/props")
            served = json.load(urllib.request.urlopen(req, timeout=30)).get("model_path", "")
        except Exception:
            served = ""
        e["served_model"] = served
        if served and os.path.basename(served) != os.path.basename(path):
            e["error"] = f"قياس باطل: بيخدم {served}"
            A.kill_servers(); rep["models"][name] = e; save(rep); continue

        try:
            for title, prompt in TESTS:
                t0 = time.time()
                try:
                    body = json.dumps({"messages": [{"role": "user", "content": prompt}],
                                       "max_tokens": 400, "temperature": 0.2}).encode("utf-8")
                    rq = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=body,
                                                headers={"Content-Type": "application/json"})
                    d = json.load(urllib.request.urlopen(rq, timeout=600))
                    el = time.time() - t0
                    ct = (d.get("usage") or {}).get("completion_tokens") or 0
                    txt = d["choices"][0]["message"].get("content") or ""
                    sc, det = score_test(title, txt)
                    e["tests"][title] = {"tok_s": round(ct / el, 1) if el else None, "seconds": round(el, 1),
                                         "score": sc, "detail": det, "text": txt[:900]}
                    print(f"  [{title}] {'%.2f' % sc if sc is not None else 'بشري'} · {ct/el:.1f} ك/ث", flush=True)
                except Exception as ex:
                    e["tests"][title] = {"error": str(ex)[:100]}
                save(rep)
        finally:
            A.kill_servers()
        # المتوسط الآلي
        sc = [v["score"] for v in e["tests"].values() if isinstance(v, dict) and v.get("score") is not None]
        sp = [v["tok_s"] for v in e["tests"].values() if isinstance(v, dict) and v.get("tok_s")]
        e["auto_score"] = round(sum(sc) / len(sc), 3) if sc else None
        e["avg_tok_s"] = round(sum(sp) / len(sp), 1) if sp else None
        rep["models"][name] = e
        save(rep)

    print("\n===== الخلاصة =====", flush=True)
    for n, e in sorted(rep["models"].items(), key=lambda x: -(x[1].get("auto_score") or 0)):
        print(f"  {n:<22} آلي={(e.get('auto_score') or 0):.2f} · {e.get('avg_tok_s')} ك/ث · {e.get('size_gb')}ج", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        import traceback; traceback.print_exc()
        save({"error": f"{type(ex).__name__}: {str(ex)[:300]}"})
