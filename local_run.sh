#!/usr/bin/env bash
# تجربة م3 كاملة محليًا على الكارت — نفس ترتيب brief §4 بأرقام §9 (F5.4)
# التشغيل:  bash local_run.sh
set -e
cd "$(dirname "$0")"
PY=${PY:-/f/projects/grow/venv/Scripts/python.exe}
D=${DATA_DIR:-F:/projects/grow/data}
export DEVICE=${DEVICE:-cuda} DATA_DIR="$D" THREADS=${THREADS:-8} VRAM_FRACTION=${VRAM_FRACTION:-0.35}

# توكنات م1 المحلية (من metrics.json) → الهدف النهائي للذراعين
BASE_TOKENS=$($PY -c "import json;print(json.load(open(r'$D/metrics.json'))['tokens_seen'])")
ARM1_EXTRA=${ARM1_EXTRA:-10000000}
ARM2_TARGET=$((BASE_TOKENS + ARM1_EXTRA))
echo "م1 المحلي: $BASE_TOKENS توكن | arm1 يكمل $ARM1_EXTRA | arm2 الهدف $ARM2_TARGET"

echo; echo "==== 4) النمو (Net2Net) + بوابة S1 ===="
CHECK_F1=0 CKPT="$D/checkpoint.pt" OUT="$D/m3/grown.pt" $PY grow.py

echo; echo "==== 3ب) تقييم الموديل المكبَّر قبل أي تدريب (مرجع S1 الحقيقي) ===="
TAG=grown0 CKPT="$D/m3/grown.pt" $PY eval.py

echo; echo "==== 5) arm1 — المكبَّر يكمّل على المخلوط ===="
INIT="$D/m3/grown.pt" INIT_MODE=weights TAG=arm1 STOP_AT_TOKENS="$ARM1_EXTRA" \
  OUT="$D/m3/arm1" DATA="$D/m3/mixed.txt" REPORT_EVERY=60 CKPT_EVERY=120 $PY arm.py
TAG=arm1 CKPT="$D/m3/arm1/ckpt.pt" $PY eval.py

echo; echo "==== 7) arm2 — من الصفر بنفس الحجم ونفس التوكنات ===="
INIT="$D/m3/grown.pt" INIT_MODE=fresh TAG=arm2 STOP_AT_TOKENS="$ARM2_TARGET" \
  OUT="$D/m3/arm2" DATA="$D/m3/mixed.txt" REPORT_EVERY=300 CKPT_EVERY=300 $PY arm.py
TAG=arm2 CKPT="$D/m3/arm2/ckpt.pt" $PY eval.py

echo; echo "==== 8) تقرير الحكم ===="
$PY local_report.py
