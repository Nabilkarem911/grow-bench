#!/bin/sh
# sysinfo.sh — يكتب موارد السيرفر الحقيقية في ملف يترفع على الريبو (بدون لمس أي حاجة)
R=/data/results
mkdir -p "$R"
{
  printf '{\n'
  printf '  "nproc": %s,\n' "$(nproc)"
  printf '  "mem_total_mb": %s,\n' "$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)"
  printf '  "mem_available_mb": %s,\n' "$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)"
  printf '  "mem_free_mb": %s,\n' "$(awk '/MemFree/{print int($2/1024)}' /proc/meminfo)"
  printf '  "swap_total_mb": %s,\n' "$(awk '/SwapTotal/{print int($2/1024)}' /proc/meminfo)"
  printf '  "disk_free_gb_data_volume": %s,\n' "$(df -BG /data 2>/dev/null | awk 'NR==2{gsub("G",""); print $4}')"
  printf '  "disk_free_gb_root": %s,\n' "$(df -BG / 2>/dev/null | awk 'NR==2{gsub("G",""); print $4}')"
  printf '  "cpu_model": "%s",\n' "$(awk -F: '/model name/{gsub(/^ +/,"",$2); print $2; exit}' /proc/cpuinfo)"
  printf '  "loadavg": "%s",\n' "$(cat /proc/loadavg)"
  printf '  "note": "فحص قراءة فقط — مفيش أي تعديل على أي حاجة"\n'
  printf '}\n'
} > "$R/sysinfo.json"
cat "$R/sysinfo.json"
