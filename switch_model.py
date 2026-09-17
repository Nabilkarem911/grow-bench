#!/usr/bin/env python3
"""switch_model.py — تبديل موديل خدمة llm.orcanox.xyz بأمر واحد (مع تحقق).

الاستخدام:
  python switch_model.py --list          # يعرض المتاح + الشغال حاليًا
  python switch_model.py --model ernie   # يبدّل ويتأكد
  python switch_model.py --stop          # يوقف الخدمة (يوفّر الرام فورًا)

المفاتيح: /data/moe/… على السيرفر · Dokploy API من ~/.env.dokploy
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

B = "https://admin.orcanox.xyz"
CID = "Ot44QAftYUxUBcyQrUCXb"
LLM_URL = "https://llm.orcanox.xyz"
LLM_KEY = "orcanox-llm-7f3a91"

# الموديلات المتاحة على السيرفر (متحقق منها بقياس فعلي)
MODELS = {
    "qwen17":  {"file": "Qwen3-1.7B-Q4_K_M.gguf",       "gb": 1.03,  "tok_s": 12.7, "note": "⭐ الأنسب للتشغيل الدائم — عربي نضيف وسريع"},
    "ernie":   {"file": "ERNIE-4.5-21B-A3B-Q4_K_M.gguf","gb": 12.57, "tok_s": 5.8,  "note": "🧠 الأذكى — JSON نضيف وعربي احترافي (ثقيل على الرام)"},
    "lfm":     {"file": "LFM2.5-1.2B-Q4_K_M.gguf",      "gb": 0.68,  "tok_s": 17.6, "note": "⚡ الأسرع — جودة عربي مقبولة"},
    "qwen4":   {"file": "Qwen3-4B-Q4_K_M.gguf",         "gb": 2.33,  "tok_s": 5.1,  "note": "متوازن"},
    "qwen35":  {"file": "Qwen3.5-4B-Q4_K_M.gguf",       "gb": 2.55,  "tok_s": 4.6,  "note": "متوازن (أحدث)"},
    "30b":     {"file": "30B-Q3_K_M.gguf",              "gb": 13.11, "tok_s": 4.4,  "note": "كبير ومضغوط"},
    "ling":    {"file": "Ling-mini-2.0-Q4_K_M.gguf",    "gb": 9.26,  "tok_s": 15.0, "note": "⚠️ سريع لكن عربيته مكسّرة"},
    "granite": {"file": "granite-4.0-1b-Q4_K_M.gguf",   "gb": 0.95,  "tok_s": 11.0, "note": "⚠️ عربيته مكسّرة"},
}


def api(path, body=None, key=None):
    tok = key or os.environ.get("DOKPLOY_API_KEY")
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body else None,
                                 headers={"x-api-key": tok, "Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(req, timeout=90))


def live_model():
    try:
        req = urllib.request.Request(LLM_URL + "/props", headers={"Authorization": "Bearer " + LLM_KEY})
        return json.load(urllib.request.urlopen(req, timeout=30)).get("model_path", "")
    except Exception:
        return None


def set_env(**kw):
    env = api(f"/api/compose.one?composeId={CID}").get("env", "")
    for k, v in kw.items():
        env = re.sub(rf"{k}=.*", f"{k}={v}", env) if k in env else env.rstrip() + f"\n{k}={v}\n"
    api("/api/compose.update", {"composeId": CID, "env": env})
    api("/api/compose.deploy", {"composeId": CID})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--stop", action="store_true")
    a = ap.parse_args()

    live = live_model()
    if a.list or (not a.model and not a.stop):
        print("الموديل الشغال الآن:", (live or "الخدمة موقوفة").split("/")[-1])
        print(f"\n{'المفتاح':<9}{'الحجم':>8}{'السرعة':>8}  الوصف")
        for k, v in sorted(MODELS.items(), key=lambda x: -x[1]["gb"]):
            mark = " ← شغال" if live and live.endswith(v["file"]) else ""
            print(f"{k:<9}{v['gb']:>7.2f}ج{v['tok_s']:>7.1f}  {v['note']}{mark}")
        return

    if a.stop:
        set_env(RUN_LLM="0")
        print("⏸️ الخدمة اتوقفت — الرام اتوفّرت فورًا")
        return

    m = a.model.lower()
    if m not in MODELS:
        print(f"❌ مفتاح غير معروف: {m}\nالمتاح: {', '.join(MODELS)}")
        sys.exit(1)
    info = MODELS[m]
    print(f"بنبدّل لـ {m} ({info['file']} · {info['gb']} جيجا · {info['tok_s']} كلمة/ث)…")
    set_env(LLM_MODEL=f"/data/moe/{info['file']}", RUN_LLM=str(int(time.time()) % 10000))

    # ننتظر ونتحقق من الهوية فعلًا
    for i in range(30):
        time.sleep(10)
        got = live_model()
        if got and got.endswith(info["file"]):
            print(f"✅ اتأكد: الخدمة بتخدم {info['file']} (بعد {(i+1)*10} ثانية)")
            return
        print(f"  … بننتظر ({i+1}) · الحالي: {(got or 'لسه بيحمّل').split('/')[-1]}")
    print("⚠️ ماقدرتش أتأكد — راجع الخدمة")


if __name__ == "__main__":
    main()
