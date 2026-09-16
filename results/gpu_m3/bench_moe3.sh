#!/bin/sh
# bench_moe3.sh — الكلام العربي + اختراعنا (تخمين+تحقق) — دورة واحدة فقط (-st)
L=/f/tools/llamacpp
BIG="F:/lmstudio-models/moe/Qwen3-30B-A3B-Q4_K_M.gguf"
DRAFT="F:/lmstudio-models/moe/Qwen3-0.6B-Q8_0.gguf"
R=/f/projects/grow/data/results
P="اكتب فقرة قصيرة عن أهمية التغليف الجيد للمطاعم. /no_think"

echo "===== أ) الطريقة العادية =====" > $R/moe_ar.log
"$L/llama-cli.exe" -m "$BIG" -ngl 0 -t 8 -n 60 -st --no-warmup -p "$P" >> $R/moe_ar.log 2>&1
echo "--- (أ) خلص ---" >> $R/moe_ar.log

echo "===== ب) اختراعنا: تخمين + تحقق =====" > $R/moe_spec.log
"$L/llama-cli.exe" -m "$BIG" -md "$DRAFT" -ngl 0 -t 8 -n 60 -st --no-warmup --spec-draft-n-max 8 -p "$P" >> $R/moe_spec.log 2>&1
echo "--- (ب) خلص ---" >> $R/moe_spec.log
echo "ALLDONE"
