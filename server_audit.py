#!/usr/bin/env python3
"""server_audit.py — فحص موارد السيرفر: كل حاوية، رامها، الصور، القرص.

بيتكلم مع Docker مباشرة عبر الـsocket (من غير docker CLI)، وبيرفع التقرير
على ريبو **خاص** (orcanox-internal) — مفيش أي بيانات سيرفر على الريبو العام.

يحتاج: GITHUB_TOKEN · DOCKER_SOCK (افتراضي /var/run/docker.sock)
"""
import base64
import http.client
import json
import os
import shutil
import socket
import time
import urllib.error
import urllib.request

SOCK = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("AUDIT_REPO", "Nabilkarem911/orcanox-internal")
PATH = os.environ.get("AUDIT_PATH", "server_audit.json")


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, sock_path):
        super().__init__("localhost")
        self._sock_path = sock_path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(90)
        s.connect(self._sock_path)
        self.sock = s


def dget(c, path):
    c.request("GET", path)
    r = c.getresponse()
    raw = r.read()
    if r.status >= 400:
        raise RuntimeError(f"{path} → {r.status}: {raw[:200]}")
    return json.loads(raw)


def meminfo():
    out = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, _, v = line.partition(":")
            out[k.strip()] = int(v.split()[0]) // 1024  # ميجا
    return out


def collect():
    c = UnixHTTP(SOCK)
    rep = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "sections": {}}

    mi = meminfo()
    rep["host"] = {
        "cpu_cores": os.cpu_count(),
        "mem_total_mb": mi.get("MemTotal"),
        "mem_available_mb": mi.get("MemAvailable"),
        "mem_free_mb": mi.get("MemFree"),
        "swap_total_mb": mi.get("SwapTotal"),
        "loadavg": open("/proc/loadavg").read().strip(),
        "disk": {},
    }
    for p in ("/", "/data", "/var/lib/docker"):
        try:
            u = shutil.disk_usage(p)
            rep["host"]["disk"][p] = {"total_gb": round(u.total / 2**30, 1),
                                      "used_gb": round(u.used / 2**30, 1),
                                      "free_gb": round(u.free / 2**30, 1)}
        except Exception:
            pass

    # الحاويات
    conts = dget(c, "/containers/json?all=1")
    rows = []
    for x in conts:
        name = (x.get("Names") or ["?"])[0].lstrip("/")
        row = {"name": name, "image": x.get("Image"), "state": x.get("State"),
               "status": (x.get("Status") or "")[:40], "created": x.get("Created")}
        if x.get("State") == "running":
            try:
                st = dget(c, f"/containers/{x['Id']}/stats?stream=false")
                mem = st.get("memory_stats", {})
                used = mem.get("usage", 0)
                cache = (mem.get("stats") or {}).get("inactive_file", 0)
                row["mem_mb"] = round(max(used - cache, 0) / 2**20, 1)
                row["mem_limit_mb"] = round(mem.get("limit", 0) / 2**20, 1)
                cpu = st.get("cpu_stats", {})
                pre = st.get("precpu_stats", {})
                cd = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get("cpu_usage", {}).get("total_usage", 0)
                sd = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
                ncpu = cpu.get("online_cpus") or os.cpu_count() or 1
                row["cpu_pct"] = round((cd / sd) * ncpu * 100, 2) if sd > 0 else 0.0
            except Exception as e:
                row["stats_error"] = str(e)[:80]
        rows.append(row)
    rows.sort(key=lambda r: -(r.get("mem_mb") or 0))
    rep["containers"] = rows

    # الصور + القرص
    try:
        imgs = dget(c, "/images/json")
        rep["images"] = sorted(
            [{"repo": (t or "<none>"), "size_mb": round(i.get("Size", 0) / 2**20, 1),
              "dangling": not (i.get("RepoTags") or [])}
             for i in imgs for t in (i.get("RepoTags") or [None])],
            key=lambda i: -i["size_mb"])
        rep["images_total_gb"] = round(sum(i["size_mb"] for i in rep["images"]) / 1024, 2)
        rep["dangling_images_gb"] = round(sum(i["size_mb"] for i in rep["images"] if i["dangling"]) / 1024, 2)
    except Exception as e:
        rep["images_error"] = str(e)[:120]

    try:
        df = dget(c, "/system/df")
        rep["docker_df"] = {
            "images_gb": round(sum(i.get("Size", 0) for i in df.get("Images", [])) / 2**30, 2),
            "containers_gb": round(sum(c_.get("SizeRw", 0) for c_ in df.get("Containers", [])) / 2**30, 2),
            "volumes_gb": round(sum(v.get("UsageData", {}).get("Size", 0) for v in df.get("Volumes", [])) / 2**30, 2),
            "build_cache_gb": round(sum(b.get("Size", 0) for b in df.get("BuildCache", []) if b.get("InUse") is not True) / 2**30, 2),
            "volumes": [{"name": v.get("Name"), "gb": round(v.get("UsageData", {}).get("Size", 0) / 2**30, 2),
                         "in_use": v.get("UsageData", {}).get("RefCount", 0)}
                        for v in sorted(df.get("Volumes", []), key=lambda z: -(z.get("UsageData", {}).get("Size") or 0))[:20]],
        }
    except Exception as e:
        rep["df_error"] = str(e)[:120]

    stopped = [r for r in rows if r["state"] != "running"]
    rep["summary"] = {
        "containers_total": len(rows),
        "containers_running": len([r for r in rows if r["state"] == "running"]),
        "containers_stopped": len(stopped),
        "stopped_names": [r["name"] for r in stopped],
        "top_ram": [{"name": r["name"], "mem_mb": r.get("mem_mb")} for r in rows[:15]],
        "ram_used_by_containers_mb": round(sum(r.get("mem_mb") or 0 for r in rows), 1),
    }
    return rep


def upload(rep):
    if not TOKEN:
        print("⚠️ مفيش GITHUB_TOKEN — مش هنرفع")
        return
    api = f"https://api.github.com/repos/{REPO}/contents/{PATH}"
    h = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
         "Content-Type": "application/json", "User-Agent": "orcanox-audit"}
    sha = None
    try:
        r = urllib.request.Request(api, headers=h)
        sha = json.load(urllib.request.urlopen(r, timeout=60)).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print("⚠️ قراءة الملف:", e.code)
    body = {"message": "server audit " + rep["generated_at"],
            "content": base64.b64encode(json.dumps(rep, ensure_ascii=False, indent=1).encode()).decode()}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(api, data=json.dumps(body).encode(), headers=h, method="PUT")
    try:
        d = json.load(urllib.request.urlopen(req, timeout=90))
        print("✅ اترفع على الريبو الخاص:", d["content"]["html_url"])
    except urllib.error.HTTPError as e:
        print("❌ الرفع فشل:", e.code, e.read().decode()[:200])


def write_status(ok, detail, extra=None):
    """ملف حالة غير حساس على /data/results → بيترفع على الريبو العام (عشان أقدر أشوف الأخطاء)"""
    try:
        os.makedirs("/data/results", exist_ok=True)
        st = {"ok": ok, "detail": detail, "at": time.strftime("%H:%M:%S UTC", time.gmtime())}
        if extra:
            st.update(extra)
        with open("/data/results/audit_status.json", "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
        print("حالة مكتوبة:", st)
    except Exception as e:
        print("مش قادر أكتب الحالة:", e)


if __name__ == "__main__":
    write_status(True, "بدأ التنفيذ")
    try:
        rep = collect()
        s = rep["summary"]
        print(f"حاويات: {s['containers_running']} شغالة / {s['containers_stopped']} واقفة")
        print(f"رام الحاويات: {s['ram_used_by_containers_mb']} ميجا · متاح: {rep['host']['mem_available_mb']} ميجا")
        for r in s["top_ram"]:
            print(f"  {r['mem_mb']:>9} ميجا  {r['name']}")
        upload(rep)
        write_status(True, "تم", {"containers_running": s["containers_running"],
                                 "ram_by_containers_mb": s["ram_used_by_containers_mb"],
                                 "mem_available_mb": rep["host"]["mem_available_mb"],
                                 "images_total_gb": rep.get("images_total_gb"),
                                 "docker_df": rep.get("docker_df", {}).get("volumes_gb")})
    except Exception as e:
        import traceback
        print("❌ فشل:", e)
        traceback.print_exc()
        write_status(False, f"{type(e).__name__}: {str(e)[:300]}")
