#!/bin/sh
# llama_bench_server.sh — قياس llama.cpp على معالج السيرفر (بدون كارت شاشة).
# بيقيس: سرعة F16 مقابل Q4_K_M + جودة (perplexity) على نص عربي — وكل حاجة تتسجل على /data/results.
set -u
R=/data/results
mkdir -p "$R"
LOG="$R/llama_server_log.json"   # امتداد .json عشان الـuploader يرفعه على الريبو (المحتوى نص خام)
exec >>"$LOG" 2>&1
echo "================ بدء $(date -u +%H:%M:%S) ================"
echo "خيوط: ${THREADS:-4} | موديل: ${BENCH_GGUF_REPO:-Qwen/Qwen2.5-0.5B-Instruct-GGUF}"

apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq curl unzip >/dev/null 2>&1
echo "apt: $?"

TAG="${LLAMA_TAG:-b10988}"
URL="https://github.com/ggml-org/llama.cpp/releases/download/$TAG/llama-$TAG-bin-ubuntu-x64.tar.gz"
echo "تنزيل llama.cpp: $URL"
curl -sL --max-time 900 "$URL" -o /tmp/llama.tar.gz
echo "حجم الملف: $(wc -c </tmp/llama.tar.gz 2>/dev/null) بايت"
mkdir -p /tmp/llama && tar xzf /tmp/llama.tar.gz -C /tmp/llama && echo "فك الضغط تمام"
find /tmp/llama -maxdepth 3 -name "llama-bench" -o -maxdepth 3 -name "llama-quantize" | head -4
BIN=$(find /tmp/llama -name "llama-bench" -type f | head -1)
QUANT=$(find /tmp/llama -name "llama-quantize" -type f | head -1)
PPL=$(find /tmp/llama -name "llama-perplexity" -type f | head -1)
CLI=$(find /tmp/llama -name "llama-cli" -type f | head -1)
echo "البرامج: $BIN | $QUANT | $PPL | $CLI"
chmod +x "$BIN" "$QUANT" "$PPL" "$CLI" 2>/dev/null

HF=https://huggingface.co/${BENCH_GGUF_REPO:-Qwen/Qwen2.5-0.5B-Instruct-GGUF}/resolve/main
for F in qwen2.5-0.5b-instruct-q4_k_m.gguf qwen2.5-0.5b-instruct-fp16.gguf; do
  [ -f "/data/$F" ] || curl -sL --max-time 1800 "$HF/$F" -o "/data/$F"
  echo "$F : $(wc -c </data/$F 2>/dev/null) بايت"
done

echo "================ السرعة (llama-bench) ================"
for F in qwen2.5-0.5b-instruct-fp16.gguf qwen2.5-0.5b-instruct-q4_k_m.gguf; do
  echo "---- $F ----"
  "$BIN" -m "/data/$F" -t "${THREADS:-4}" -p 64 -n 64 -r 3 2>&1 | tail -6
done

echo "================ الجودة (perplexity على نص عربي) ================"
for F in qwen2.5-0.5b-instruct-fp16.gguf qwen2.5-0.5b-instruct-q4_k_m.gguf; do
  echo "---- $F ----"
  "$PPL" -m "/data/$F" -f /app/data/corpus_factory.txt -c 512 -t "${THREADS:-4}" 2>&1 | tail -4
done

echo "================ عينة عربية (q4) ================"
"$CLI" -m /data/qwen2.5-0.5b-instruct-q4_k_m.gguf -p "في صباح اليوم التالي" -n 40 -t "${THREADS:-4}" 2>&1 | tail -6
echo "================ خلص $(date -u +%H:%M:%S) ================"
