"""probe — يرفع محتوى /data على ntfy كل PROBE_EVERY ثانية (مراقبة بدون وصول للوجز).
م3: ينشر أيضًا أحدث ملف في /data/results/ (أول 1500 حرف)."""
import json, os, time, urllib.request

DATA_DIR = os.environ.get("DATA_DIR", "/data")
REPORT_URL = os.environ.get("REPORT_URL", "").strip()
EVERY = int(os.environ.get("PROBE_EVERY", "60"))


def snap():
    out = {"stage": "probe", "files": {}}
    for root, _, files in os.walk(DATA_DIR):
        for fn in files:
            fp = os.path.join(root, fn)
            try:
                out["files"][os.path.relpath(fp, DATA_DIR)] = os.path.getsize(fp)
            except OSError:
                pass
    for name in ("state", "report"):
        p = os.path.join(DATA_DIR, "factory", name + ".json")
        if os.path.exists(p):
            try:
                out[name] = json.load(open(p, encoding="utf-8"))
            except Exception as e:
                out[name] = f"unreadable: {e}"
    rdir = os.path.join(DATA_DIR, "results")
    if os.path.isdir(rdir):
        try:
            rfiles = [os.path.join(rdir, f) for f in os.listdir(rdir)
                      if f.endswith(".json") and not f.endswith(".tmp")]
            if rfiles:
                newest = max(rfiles, key=os.path.getmtime)
                out["latest_result"] = os.path.basename(newest)
                out["latest_result_body"] = open(
                    newest, encoding="utf-8", errors="replace").read()[:1500]
        except Exception as e:
            out["latest_result"] = f"unreadable: {e}"
    return out


while True:
    payload = snap()
    body = json.dumps(payload, ensure_ascii=False)
    print("PROBE " + body[:500], flush=True)
    if REPORT_URL:
        try:
            req = urllib.request.Request(REPORT_URL, data=body.encode("utf-8"),
                                         headers={"Title": "grow probe"})
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print("probe-warn:", e, flush=True)
    time.sleep(EVERY)
