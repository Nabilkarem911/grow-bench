#!/usr/bin/env python3
"""patch_experts.py — يعدّل عدد الخبراء الفعّالين في ملف GGUF (في مكانه، من غير إعادة كتابة الملف).

بيقرا رأس الملف بس ويغيّر القيمة، فالتعديل فوري مهما كان حجم الملف.

الاستخدام: patch_experts.py <المصدر> <الهدف> <عدد الخبراء الجديد>
"""
import os
import shutil
import struct
import sys

TYPES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
KEY = "qwen3moe.expert_used_count"


def read_str(f):
    n = struct.unpack("<Q", f.read(8))[0]
    return f.read(n).decode("utf-8", "replace")


def skip_value(f, t):
    if t in (8,):
        read_str(f)
    elif t == 9:
        et = struct.unpack("<I", f.read(4))[0]
        cnt = struct.unpack("<Q", f.read(8))[0]
        for _ in range(cnt):
            if et == 8:
                read_str(f)
            else:
                f.seek(TYPES[et], 1)
    elif t in TYPES:
        f.seek(TYPES[t], 1)
    else:
        raise ValueError(f"نوع غير معروف: {t}")


def main():
    src, dst, new_n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    if not os.path.exists(src):
        print(f"❌ المصدر مش موجود: {src}")
        return 1
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        print(f"بنعمل نسخة: {dst}")
        shutil.copyfile(src, dst)
    else:
        print(f"النسخة موجودة بالفعل: {dst}")

    with open(dst, "r+b") as f:
        assert f.read(4) == b"GGUF", "الملف مش GGUF"
        ver = struct.unpack("<I", f.read(4))[0]
        n_tensors = struct.unpack("<Q", f.read(8))[0]
        n_kv = struct.unpack("<Q", f.read(8))[0]
        print(f"GGUF v{ver} · موترات={n_tensors} · حقول={n_kv}")
        for _ in range(n_kv):
            k = read_str(f)
            t = struct.unpack("<I", f.read(4))[0]
            if k == KEY:
                if t != 4:
                    print(f"❌ نوع القيمة غير متوقع: {t}")
                    return 1
                pos = f.tell()
                old = struct.unpack("<I", f.read(4))[0]
                f.seek(pos)
                f.write(struct.pack("<I", new_n))
                f.flush()
                print(f"✅ {KEY}: {old} → {new_n}")
                return 0
            skip_value(f, t)
    print(f"❌ مش لاقي الحقل {KEY}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
