"""push — يرفع نتائج /data على الريبو عبر Git Data API (باكب للأصول، بدون SSH).
يشتغل كل PUSH_EVERY ثانية لحد PUSH_MAX_SECONDS ثم يخرج. الملفات المتغيرة فقط."""
import base64, hashlib, json, os, time, urllib.request

DATA_DIR = os.environ.get("DATA_DIR", "/data")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPO", "Nabilkarem911/grow-bench").strip()
BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()
EVERY = int(os.environ.get("PUSH_EVERY", "120"))
MAX_SECONDS = int(os.environ.get("PUSH_MAX_SECONDS", "10800"))
REPORT_URL = os.environ.get("REPORT_URL", "").strip()

API = f"https://api.github.com/repos/{REPO}"


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def blob_sha(content):
    return hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest()


def local_files():
    """{repo_path: (abs_path, bytes)} للملفات المطلوب نسخها."""
    out = {}
    rdir = os.path.join(DATA_DIR, "results")
    if os.path.isdir(rdir):
        for f in sorted(os.listdir(rdir)):
            if f.endswith(".json") and not f.endswith(".tmp"):
                p = os.path.join(rdir, f)
                out[f"results/{f}"] = p
    fc = os.path.join(DATA_DIR, "factory", "corpus_factory.txt")
    if os.path.exists(fc):
        out["data/corpus_factory.txt"] = fc
    fr = os.path.join(DATA_DIR, "factory", "report.json")
    if os.path.exists(fr):
        out["data/factory_report.json"] = fr
    for sub in ("ft", "m3"):
        sdir = os.path.join(DATA_DIR, sub)
        if os.path.isdir(sdir):
            for f in sorted(os.listdir(sdir)):
                if f.endswith(".json") and not f.endswith(".tmp"):
                    out[f"data/{sub}/{f}"] = os.path.join(sdir, f)
    res = {}
    for rp, ap in out.items():
        try:
            res[rp] = open(ap, "rb").read()
        except OSError:
            pass
    return res


def push_once():
    files = local_files()
    if not files:
        return "no files"
    ref = api("GET", f"/git/ref/heads/{BRANCH}")
    commit_sha = ref["object"]["sha"]
    commit = api("GET", f"/git/commits/{commit_sha}")
    tree = api("GET", f"/git/trees/{commit['tree']['sha']}?recursive=1")
    remote = {e["path"]: e["sha"] for e in tree.get("tree", [])}
    if tree.get("truncated"):
        raise RuntimeError("repo tree truncated")

    entries = []
    for rp, content in sorted(files.items()):
        if remote.get(rp) == blob_sha(content):
            continue
        b = api("POST", "/git/blobs", {
            "content": base64.b64encode(content).decode(), "encoding": "base64"})
        entries.append({"path": rp, "mode": "100644", "type": "blob", "sha": b["sha"]})
    if not entries:
        return "unchanged"

    new_tree = api("POST", "/git/trees",
                   {"base_tree": commit["tree"]["sha"], "tree": entries})
    new_commit = api("POST", "/git/commits", {
        "message": f"grow: /data snapshot ({len(entries)} files)",
        "tree": new_tree["sha"], "parents": [commit_sha],
        "author": {"name": "grow-push", "email": "grow@local"}})
    api("PATCH", f"/git/refs/heads/{BRANCH}", {"sha": new_commit["sha"]})
    return f"pushed {len(entries)} files: {[e['path'] for e in entries]}"


def note(msg):
    print("PUSH " + msg, flush=True)
    if REPORT_URL:
        try:
            req = urllib.request.Request(REPORT_URL, data=json.dumps(
                {"stage": "push", "detail": msg}, ensure_ascii=False).encode(),
                headers={"Title": "grow push"})
            urllib.request.urlopen(req, timeout=15)
        except Exception:
            pass


def main():
    if not TOKEN:
        note("skipped: no GITHUB_TOKEN")
        return
    t0 = time.time()
    while True:
        try:
            note(push_once())
        except Exception as e:
            note(f"error: {type(e).__name__}: {e}")
        if time.time() - t0 > MAX_SECONDS:
            note("done: max seconds reached")
            return
        time.sleep(EVERY)


if __name__ == "__main__":
    main()
