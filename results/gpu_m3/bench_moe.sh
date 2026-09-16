#!/bin/sh
# bench_moe.sh — قياس موديل «الجزء الفعّال» (30B-A3B) على المعالج بدون كارت شاشة.
# الهدف: (1) هل بيشتغل وسريع قد إيه؟ (2) هل التخزين المؤقت للخبراء بيفرق؟ (3) هل التخمين+التحقق بيسرّع؟
L=/f/tools/llamacpp
M=/f/lmstudio-models/moe
BIG=$M/Qwen3-30B-A3B-Q4_K_M.gguf
DRAFT=$M/Qwen3-0.6B-Q8_0.gguf
R=/f/projects/grow/data/results/moe_bench
mkdir -p $R
P="اكتب فقرة قصيرة عن أهمية التغليف الجيد للمطاعم:"

echo "############ ١) أساسي: ٤ خيوط (ظرف السيرفر) — معالج فقط ############"
$L/llama-bench.exe -m "$BIG" -ngl 0 -t 4 -p 32 -n 32 -r 2 -o md 2>&1 | grep -E "^\|" | head -6

echo "############ ٢) أساسي: ٨ خيوط (أقصى الجهاز) — معالج فقط ############"
$L/llama-bench.exe -m "$BIG" -ngl 0 -t 8 -p 32 -n 32 -r 2 -o md 2>&1 | grep -E "^\|" | head -6

echo "############ ٣) توليد عربي حقيقي (٨ خيوط) ############"
$L/llama-cli.exe -m "$BIG" -ngl 0 -t 8 -n 90 -no-cnv -p "$P" 2>&1 | grep -E "eval time|total time|tokens per second|^[^[]" | tail -12

echo "############ ٤) اختراعنا: تخمين ٨ كلمات + تحقق مرة واحدة ############"
$L/llama-cli.exe -m "$BIG" -md "$DRAFT" -ngl 0 -t 8 -n 90 -no-cnv --spec-draft-n-max 8 -p "$P" \
  2>&1 | grep -E "eval time|total time|tokens per second|draft|^[^[]" | tail -14

echo "############ ٥) نفس رقم ٣ بالظبط (نتأكد من ثبات القياس) ############"
$L/llama-cli.exe -m "$BIG" -ngl 0 -t 8 -n 90 -no-cnv -p "$P" 2>&1 | grep -E "eval time|tokens per second" | tail -4
echo "=== خلص القياس ==="
