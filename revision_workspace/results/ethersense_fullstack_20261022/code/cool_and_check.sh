#!/bin/sh
set -eu
OWNER=20261022_685511
PREP=/root/ethersense/wifi_detection_20261021/cooling_prepare.sh
RESTORE=/root/ethersense/wifi_detection_20261021/cooling_restore.sh
[ -f "$PREP" ] && [ -f "$RESTORE" ]
cleanup() { sh "$RESTORE" "$OWNER"; }
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
sh "$PREP" "$OWNER"
echo COOLING_BEGIN
for sample in 0 1 2 3 4; do
  date -u
  cat /sys/class/thermal/thermal_zone0/temp
  cat /proc/sys/kernel/random/boot_id
  if [ "$sample" -lt 4 ]; then sleep 10; fi
done
echo HACKRF_IDENTITY
if command -v timeout >/dev/null 2>&1; then timeout 8 /root/ethersense/bin/hackrf_info; else /root/ethersense/bin/hackrf_info; fi
echo COOLING_CHECK_END
