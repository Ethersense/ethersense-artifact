#!/bin/sh
set -eu
TRIAL="$1"
case "$TRIAL" in ""|*[!A-Za-z0-9_]*) exit 2;; esac
OUT=/tmp/ethersense_ap_$TRIAL
[ ! -e "$OUT" ] || { echo TRIAL_ALREADY_EXISTS; exit 3; }
TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
MEM=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
[ "$TEMP" -lt 60000 ] && [ "$MEM" -ge 65536 ] || { echo PRECONDITION_FAILED; exit 4; }
if pidof hackrf_transfer >/dev/null; then echo CAPTURE_ALREADY_RUNNING; exit 5; fi
mkdir "$OUT"
echo ROUTER_TRIAL_BEGIN
cat /proc/sys/kernel/random/boot_id > "$OUT/boot_id.txt"
cat /proc/uptime > "$OUT/uptime_start.txt"
/root/ethersense/bin/hackrf_transfer -r "$OUT/capture.cs8" -f 20000000 -s 20000000 -n 20000000 -l 16 -g 4 -a 0 > "$OUT/capture_stdout.txt" 2> "$OUT/capture_stderr.txt"
BYTES=$(wc -c < "$OUT/capture.cs8")
[ "$BYTES" = 40000000 ] || { echo WRONG_CAPTURE_BYTES=$BYTES; exit 6; }
cat /proc/uptime > "$OUT/uptime_capture_end.txt"
/root/ethersense/bin/es_psd -N 4096 -r 1.0 -s 20000000 -p "$OUT/psd.bin" < "$OUT/capture.cs8" > "$OUT/psd_report.txt" 2> "$OUT/psd_stderr.txt"
cat /proc/uptime > "$OUT/uptime_psd_end.txt"
cat /sys/class/thermal/thermal_zone0/temp > "$OUT/temperature_end.txt"
(cd "$OUT"; sha256sum capture.cs8 psd.bin capture_stdout.txt capture_stderr.txt psd_report.txt psd_stderr.txt boot_id.txt uptime_start.txt uptime_capture_end.txt uptime_psd_end.txt temperature_end.txt > SHA256SUMS)
echo ROUTER_OUTPUT=$OUT
cat "$OUT/SHA256SUMS"
cat "$OUT/psd_report.txt"
echo ROUTER_TRIAL_END
