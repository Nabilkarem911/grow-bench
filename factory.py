"""
م2 — مصنع البيانات: المعلّم (OpenAI-compatible API) ينتج نصوصًا عربية نظيفة.
- بذور متنوعة (نوع مهمة × موضوع) → مكالمات API → فلترة جودة → out.jsonl + corpus_factory.txt
- حالة قابلة للاستكمال (state.json) — أي توقف يكمل من آخر بذرة.
- سقف مكالمات/وقت + تقارير ntfy دورية + تقرير جودة نهائي.
- stdlib فقط — لا يحتاج تثبيت حزم.
"""
import hashlib, json, os, random, re, signal, time, urllib.request

DATA_DIR = os.environ.get("DATA_DIR", "/data")
BASE_URL = os.environ.get("TEACHER_BASE_URL", "https://aihubmix.com/v1").rstrip("/")
API_KEY = os.environ.get("TEACHER_API_KEY", "").strip()
MODEL = os.environ.get("TEACHER_MODEL", "qwen3.8-flash")
MAX_CALLS = int(os.environ.get("MAX_CALLS", "500"))
MAX_SECONDS = int(os.environ.get("FACTORY_SECONDS", "7200"))
REPORT_EVERY = int(os.environ.get("REPORT_EVERY", "600"))
MAX_TOKENS = int(os.environ.get("TEACHER_MAX_TOKENS", "1400"))
REPORT_URL = os.environ.get("REPORT_URL", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

FDIR = os.path.join(DATA_DIR, "factory")
OUT_PATH = os.path.join(FDIR, "out.jsonl")
CORPUS_PATH = os.path.join(FDIR, "corpus_factory.txt")
STATE_PATH = os.path.join(FDIR, "state.json")
REPORT_PATH = os.path.join(FDIR, "report.json")
STOP = False
REPORT_DIAG = {"url_set": bool(REPORT_URL), "ntfy": "never", "tg": "never"}


def _sig(*_):
    global STOP
    STOP = True


signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)

KINDS = [
    ("شرح", "اشرح الموضوع التالي بأسلوب مبسط وواضح"),
    ("حوار", "اكتب حوارًا بين شخصين حول الموضوع التالي"),
    ("أسئلة وأجوبة", "اكتب أربعة أسئلة شائعة حول الموضوع التالي مع إجابات قصيرة دقيقة"),
    ("قصة", "اكتب قصة قصيرة متماسكة تدور حول الموضوع التالي"),
    ("خطوات", "اكتب خطوات عملية مرقمة تتعلق بالموضوع التالي"),
    ("وصف", "اكتب وصفًا تفصيليًا للموضوع التالي"),
    ("مقارنة", "قارن بين جانبين أو أكثر في الموضوع التالي"),
    ("رأي", "اكتب رأيًا مدعومًا بحجج واضحة حول الموضوع التالي"),
]
TOPICS = [
    "النظام الشمسي", "تاريخ الحضارة الإسلامية", "جغرافيا الوطن العربي", "فنون الطبخ",
    "كرة القدم", "أساسيات البرمجة", "الذكاء الاصطناعي", "صحة القلب",
    "التغذية السليمة", "الاقتصاد المنزلي", "التجارة الإلكترونية", "الأدب العربي",
    "الشعر الجاهلي", "مدارس الفلسفة", "تربية الأطفال", "الزراعة المستدامة",
    "البحر الأحمر", "الصحراء الكبرى", "وسائل النقل الحديثة", "الطاقة المتجددة",
    "التغير المناخي", "قواعد اللغة العربية", "الرياضيات في الحياة", "الفن الإسلامي",
    "الموسيقى العربية", "العمارة القديمة", "الأمن السيبراني", "ألعاب الفيديو",
    "السفر والسياحة", "الحيوانات المهددة", "النباتات الطبية", "المخترعات الحديثة",
    "الجامعات العريقة", "الأسواق الشعبية", "مهارات العمل", "الصحة النفسية",
    "الأمثال العربية", "علم الفلك", "تاريخ الطباعة", "الملاحة القديمة",
]
LEVELS = ["بلغة بسيطة للمبتدئين", "بمستوى متوسط", "بعمق وتفصيل"]
BAD_MARKERS = ["آسف", "لا أستطيع", "عذرًا، لا", "I'm sorry", "I cannot", "I can't"]

PROMPT = ("{instruction}: {topic} — {level}.\n"
          "اكتب باللغة العربية الفصحى فقط، نصًا مفيدًا ودقيقًا بطول 250 إلى 450 كلمة تقريبًا، "
          "بدون مقدمات مثل «بالطبع» أو «إليك»، وبدون أي شرح للمهمة أو تعليق خارجي.")


def build_seeds():
    seeds = [(k, i, t, lv) for lv in LEVELS for (k, i) in KINDS for t in TOPICS]
    random.Random(7).shuffle(seeds)
    return seeds


def report(payload, tg=True):
    body = json.dumps(payload, ensure_ascii=False)
    print("REPORT " + body, flush=True)
    REPORT_DIAG["url_set"] = bool(REPORT_URL)
    if REPORT_URL:
        try:
            req = urllib.request.Request(REPORT_URL, data=body.encode("utf-8"),
                                         headers={"Title": "grow M2 factory"})
            urllib.request.urlopen(req, timeout=20)
            REPORT_DIAG["ntfy"] = "ok"
        except Exception as e:
            REPORT_DIAG["ntfy"] = f"{type(e).__name__}: {e}"
            print("report-warn:", e, flush=True)
    if tg and TG_TOKEN and TG_CHAT:
        try:
            txt = ("🏭 grow M2 — مصنع البيانات\n"
                   f"stage: {payload.get('stage')} · model: {MODEL}\n"
                   f"calls: {payload.get('calls')} · accepted: {payload.get('accepted')} "
                   f"· rejected: {payload.get('rejected')}\n"
                   f"chars: {payload.get('chars'):,} · out_tok: {payload.get('out_tok'):,}\n"
                   f"{payload.get('error','')}"[:900])
            import urllib.parse
            data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": txt}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                   data=data, timeout=20)
            REPORT_DIAG["tg"] = "ok"
        except Exception as e:
            REPORT_DIAG["tg"] = f"{type(e).__name__}: {e}"
            print("telegram-warn:", e, flush=True)


def call_teacher(prompt):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.9,
        "reasoning_effort": "none",
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {API_KEY}",
                 "Content-Type": "application/json; charset=utf-8"})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read())
    msg = d.get("choices", [{}])[0].get("message", {})
    u = d.get("usage", {}) or {}
    return (msg.get("content") or "").strip(), u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


def arabic_ratio(text):
    ar = len(re.findall(r"[\u0600-\u06FF]", text))
    letters = len(re.findall(r"[^\W\d_]", text, flags=re.UNICODE))
    return ar / max(letters, 1)


def acceptable(text):
    if len(text) < 350 or len(text) > 12000:
        return False
    if arabic_ratio(text) < 0.65:
        return False
    return not any(m in text for m in BAD_MARKERS)


def load_state():
    st = {"next": 0, "calls": 0, "accepted": 0, "rejected": 0,
          "in_tok": 0, "out_tok": 0, "chars": 0, "kinds": {}}
    if os.path.exists(STATE_PATH):
        try:
            st.update(json.load(open(STATE_PATH)))
        except Exception:
            pass
    return st


def save_state(st):
    st["report_diag"] = REPORT_DIAG
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def load_seen():
    seen = set()
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(hashlib.sha1(json.loads(line)["text"][:400].encode()).hexdigest())
                except Exception:
                    pass
    return seen


def main():
    os.makedirs(FDIR, exist_ok=True)
    if not API_KEY:
        report({"stage": "failed", "error": "TEACHER_API_KEY empty"})
        return
    seeds = build_seeds()
    st = load_state()
    seen = load_seen()
    t0 = time.time()
    report({"stage": "started", "model": MODEL, "seeds_total": len(seeds),
            "resume_from": st["next"], "calls": st["calls"], "accepted": st["accepted"],
            "chars": st["chars"], "out_tok": st["out_tok"]}, tg=False)
    last_rep = time.time()

    while st["next"] < len(seeds) and st["calls"] < MAX_CALLS \
            and time.time() - t0 < MAX_SECONDS and not STOP:
        kind, instr, topic, level = seeds[st["next"]]
        st["next"] += 1
        prompt = PROMPT.format(instruction=instr, topic=topic, level=level)
        try:
            text, itok, otok = call_teacher(prompt)
        except Exception as e:
            print("api-warn:", e, flush=True)
            st["calls"] += 1
            st["rejected"] += 1
            time.sleep(3)
            continue
        st["calls"] += 1
        st["in_tok"] += itok
        st["out_tok"] += otok
        h = hashlib.sha1(text[:400].encode()).hexdigest()
        if acceptable(text) and h not in seen:
            seen.add(h)
            st["accepted"] += 1
            st["chars"] += len(text)
            st["kinds"][kind] = st["kinds"].get(kind, 0) + 1
            rec = {"id": st["accepted"], "kind": kind, "topic": topic,
                   "level": level, "chars": len(text), "text": text}
            with open(OUT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            with open(CORPUS_PATH, "a", encoding="utf-8") as f:
                f.write(text + "\n\n")
        else:
            st["rejected"] += 1
        save_state(st)

        if time.time() - last_rep >= REPORT_EVERY:
            report({"stage": "running", "model": MODEL, "calls": st["calls"],
                    "accepted": st["accepted"], "rejected": st["rejected"],
                    "chars": st["chars"], "in_tok": st["in_tok"],
                    "out_tok": st["out_tok"], "progress": f"{st['next']}/{len(seeds)}",
                    "elapsed_min": round((time.time() - t0) / 60, 1)}, tg=False)
            last_rep = time.time()
        time.sleep(0.5)

    samples = []
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()][-3:]
        samples = [{"kind": r["kind"], "topic": r["topic"], "text": r["text"][:500]}
                   for r in lines]
    res = {"stage": "stopped" if STOP else "done", "model": MODEL,
           "calls": st["calls"], "accepted": st["accepted"], "rejected": st["rejected"],
           "accept_rate": round(st["accepted"] / max(st["calls"], 1), 3),
           "chars": st["chars"], "in_tok": st["in_tok"], "out_tok": st["out_tok"],
           "kinds": st["kinds"], "elapsed_min": round((time.time() - t0) / 60, 1),
           "samples": samples}
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    report(res)


if __name__ == "__main__":
    main()
