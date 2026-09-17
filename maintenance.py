#!/usr/bin/env python3
"""maintenance.py — فحص السيرفر + تنظيف الصور والكاش غير المستخدم.

بيشتغل جوّه نفس الأداة (server_audit) وبيتكلم مع Docker عبر الـsocket.
بيعمل:
  1) فحص شامل (رام/قرص/حاويات)
  2) حذف الصور غير المستخدمة (dangling + اللي مفيش حاوية بتستخدمها)
  3) تنظيف كاش البناء (build cache)
  4) تقرير قبل/بعد على الريبو الخاص + حالة مختصرة على العام

⚠️ مابيلمسش الأحجام (volumes) — دي ممكن تحتوي بيانات مشاريع.
"""
import json
import os
import sys
import time

sys.path.insert(0, "/app")
import server_audit as SA  # noqa: E402


def main():
    c = SA.UnixHTTP(SA.SOCK)
    before = {}
    try:
        df = SA.dget(c, "/system/df")
        before = {
            "images_gb": round(sum(i.get("Size", 0) for i in df.get("Images", [])) / 2**30, 2),
            "build_cache_gb": round(sum(b.get("Size", 0) for b in df.get("BuildCache", [])) / 2**30, 2),
            "volumes_gb": round(sum(v.get("UsageData", {}).get("Size", 0) for v in df.get("Volumes", [])) / 2**30, 2),
        }
        print("قبل:", before)
    except Exception as e:
        print("قراءة df فشلت:", e)

    # الصور المستخدمة فعلاً
    used = set()
    for x in SA.dget(c, "/containers/json?all=1"):
        used.add(x.get("ImageID"))
    imgs = SA.dget(c, "/images/json")

    dangling, unused, in_use = [], [], []
    for i in imgs:
        iid = i.get("Id")
        tags = i.get("RepoTags") or []
        rec = {"id": iid[:19], "tags": tags, "size_mb": round(i.get("Size", 0) / 2**20, 1)}
        if iid in used:
            in_use.append(rec)
        elif not tags or tags == ["<none>:<none>"]:
            dangling.append(rec)
        else:
            unused.append(rec)

    print(f"\nصور: {len(imgs)} (مستخدمة {len(in_use)} · غير مستخدمة {len(unused)} · يتيمة {len(dangling)})")
    print(f"حجم اليتيمة: {sum(r['size_mb'] for r in dangling)/1024:.2f} جيجا · غير المستخدمة: {sum(r['size_mb'] for r in unused)/1024:.2f} جيجا")

    deleted, failed = [], []
    for rec in dangling + unused:
        try:
            c.request("DELETE", f"/images/{rec['id']}?force=0&noprune=0")
            r = c.getresponse()
            body = r.read()
            if r.status < 400:
                deleted.append(rec)
                print(f"  ✅ اتحذفت: {rec['tags'] or ['(يتيمة)']} ({rec['size_mb']} ميجا)")
            else:
                failed.append({**rec, "err": f"{r.status} {body[:120]}"})
                print(f"  ⚠️ فشل: {rec['tags']} → {r.status}")
        except Exception as e:
            failed.append({**rec, "err": str(e)[:120]})
            print(f"  ⚠️ استثناء: {rec['tags']} → {str(e)[:80]}")

    # كاش البناء
    cache_freed = 0
    try:
        c.request("POST", "/build/prune")
        r = c.getresponse()
        d = json.loads(r.read() or b"{}")
        cache_freed = round(sum(x.get("Size", 0) for x in (d.get("CachesDeleted") or [])) / 2**30, 2)
        if not cache_freed:
            cache_freed = round((d.get("SpaceReclaimed") or 0) / 2**30, 2)
        print(f"🧹 كاش البناء: اتحذف {cache_freed} جيجا")
    except Exception as e:
        print("تنظيف الكاش فشل:", str(e)[:100])

    rep = SA.collect()
    try:
        df2 = SA.dget(c, "/system/df")
        after = {
            "images_gb": round(sum(i.get("Size", 0) for i in df2.get("Images", [])) / 2**30, 2),
            "build_cache_gb": round(sum(b.get("Size", 0) for b in df2.get("BuildCache", [])) / 2**30, 2),
            "volumes_gb": round(sum(v.get("UsageData", {}).get("Size", 0) for v in df2.get("Volumes", [])) / 2**30, 2),
        }
    except Exception:
        after = {}
    print("بعد:", after)

    rep["maintenance"] = {
        "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "df_before": before, "df_after": after,
        "deleted_count": len(deleted), "deleted_gb": round(sum(r["size_mb"] for r in deleted) / 1024, 2),
        "deleted": deleted, "failed": failed, "build_cache_freed_gb": cache_freed,
    }
    # الرفع على الريبو الخاص
    SA.PATH = os.environ.get("AUDIT_PATH", "server_audit.json")
    SA.upload(rep)
    s = rep["summary"]
    SA.write_status(True, "صيانة تمت", {
        "containers_running": s["containers_running"],
        "ram_by_containers_mb": s["ram_used_by_containers_mb"],
        "mem_available_mb": rep["host"]["mem_available_mb"],
        "disk_free_gb": rep["host"]["disk"].get("/", {}).get("free_gb"),
        "images_gb_after": after.get("images_gb"),
        "images_deleted_gb": rep["maintenance"]["deleted_gb"],
        "build_cache_freed_gb": cache_freed,
    })


if __name__ == "__main__":
    SA.write_status(True, "بدأت الصيانة")
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        SA.write_status(False, f"{type(e).__name__}: {str(e)[:300]}")
