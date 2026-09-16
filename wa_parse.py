"""
wa_parse.py — يحوّل شات واتساب لملف منظّم + إحصائيات.
ملاحظة أمان: البيانات دي خاصة — تفضل محلية وممنوع تدخل أي ريبو عام.
"""
import json, re, statistics, sys
from collections import Counter

SRC = sys.argv[1] if len(sys.argv) > 1 else "F:/projects/grow/data/wa/WhatsApp Chat with G.pack & Modern.txt"
OUT = "F:/projects/grow/data/wa/parsed.jsonl"

# سطر رسالة: 12/14/25, 11:32 AM - المرسل: النص   (وتفاصيل النظام بدون مرسل)
RX = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2})\s*(AM|PM|ص|م)\s*-\s*(.*)$", re.S)
SYSTEM_MARK = ["Messages and calls are end-to-end encrypted", "created group", "added you",
               "changed the subject", "changed this group", "You were added", "joined using this group's invite link",
               "changed the group description", "Messages to this chat and calls are now secured"]

msgs = []
buf = None
for raw in open(SRC, encoding="utf-8", errors="replace"):
    line = raw.rstrip("\r\n")
    m = RX.match(line)
    if m:
        if buf:
            msgs.append(buf)
        date, time, ap, rest = m.groups()
        if any(s in rest for s in SYSTEM_MARK) and ":" not in rest.split(" ")[0]:
            sender, text = None, rest
        elif ": " in rest:
            sender, text = rest.split(": ", 1)
        elif ":" in rest[:40]:
            sender, text = rest.split(":", 1); text = text.lstrip()
        else:
            sender, text = None, rest
        buf = {"date": date, "time": time, "ampm": ap, "sender": sender, "text": text}
    else:
        if buf is not None:
            buf["text"] += "\n" + line
if buf:
    msgs.append(buf)

for i, m in enumerate(msgs):
    m["i"] = i
    m["len_chars"] = len(m["text"])
    m["ar_chars"] = len(re.findall(r"[\u0600-\u06FF]", m["text"]))
    m["ar_ratio"] = round(m["ar_chars"] / max(m["len_chars"], 1), 3)
    m["is_system"] = m["sender"] is None
    t = m["text"].strip()
    m["is_media"] = "<Media omitted>" in t or t in ("", "This message was deleted", "You deleted this message")
    m["has_link"] = bool(re.search(r"https?://|www\.", t))
    m["has_number"] = bool(re.search(r"\d", t))
    m["is_short_ack"] = len(t) <= 12 and bool(re.search(r"^(تمام|اوك|أوك|طيب|شكرا|شكرًا|حاضر|ماشي|ok|👍|🙏)", t))

with open(OUT, "w", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")

real = [m for m in msgs if not m["is_system"] and not m["is_media"]]
print(f"إجمالي السطور المنظّمة: {len(msgs)}")
print(f"  ├ رسائل نظام: {sum(1 for m in msgs if m['is_system'])}")
print(f"  ├ وسائط/محذوف: {sum(1 for m in msgs if m['is_media'])}")
print(f"  └ رسائل فيها كلام فعلي: {len(real)}")
print(f"\nالأطراف (أعلى 8):")
for s, c in Counter(m["sender"] for m in real).most_common(8):
    print(f"  {c:>5}  {s[:50]}")
ar = [m["ar_ratio"] for m in real]
print(f"\nنسبة العربي (متوسط): {statistics.mean(ar):.2f} | عربي غالب (>0.5): {sum(1 for r in ar if r>0.5)}/{len(ar)}")
ln = [m["len_chars"] for m in real]
print(f"الطول: متوسط {statistics.mean(ln):.0f} حرف | وسيط {statistics.median(ln):.0f} | أطول {max(ln)}")
print(f"فيه لينك: {sum(1 for m in real if m['has_link'])} | فيه أرقام: {sum(1 for m in real if m['has_number'])} | ردود قصيرة: {sum(1 for m in real if m['is_short_ack'])}")
print(f"\nكتبت {len(msgs)} رسالة منظّمة في: {OUT}")
