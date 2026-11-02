#!/bin/sh
set -eu
OWNER=20261022_685512
PREP=/root/ethersense/wifi_detection_20261021/cooling_prepare.sh
RESTORE=/root/ethersense/wifi_detection_20261021/cooling_restore.sh
if [ "${1:-}" = restore_watchdog ]; then
  sleep 300
  sh "$RESTORE" "$OWNER"
  exit
fi
sh "$PREP" "$OWNER"
nohup sh "$0" restore_watchdog > /tmp/ethersense_fs_fan_watchdog.log 2>&1 < /dev/null &
WATCHDOG_PID=$!
echo FAN_RESTORE_WATCHDOG_PID=$WATCHDOG_PID
sleep 3
echo ACTIVE_FAN_STATE
cat /sys/class/thermal/cooling_device0/cur_state
echo CURRENT_TEMP
cat /sys/class/thermal/thermal_zone0/temp
echo FAN_TARGET
uci get glfan.globals.temperature
echo COOLING_LEASE_READY
