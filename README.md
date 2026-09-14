# grow-bench — تدريب موديل لغوي عربي صغير على CPU

مشروع «الموديل اللي بيكبر»: موديل عربي ملكنا، يتدرّب على CPU ويكبر تدريجيًا.

- `bench.py` — **م0**: قياس سرعة التدريب الحقيقية (تم: ~1,564 توكن/ث على 2 threads).
- `train.py` — **م1**: تدريب فعلي لموديل ~5M باراميتر على **mC4 العربي** لساعات طويلة، مع:
  - كاش للكوربوس + checkpoints دورية في volume دائم (`/data`) + استكمال تلقائي بعد أي توقف.
  - تقارير `ntfy` كل `REPORT_EVERY` ثانية: توكنات، سرعة، train/val loss، زمن، موارد، وعينة توليد.
  - عينات توليد ثابتة (5 prompts) في التقرير النهائي للمقارنة.
- `docker-compose.yml` — كونتينر CPU-only + volume `grow_data` + `restart: unless-stopped`.

**env:** `TRAIN_SECONDS` (افتراضي 8h) · `THREADS` (3) · `TARGET_CHARS` (40M) · `REPORT_EVERY` (900s) · `CKPT_EVERY` (600s).

> مشروع بحثي لـ Orcanox — فوكس (Hermes) · 2026-09-14
