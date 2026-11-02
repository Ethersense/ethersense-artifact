#!/bin/sh
set -eu
LEASE=/tmp/ethersense_v4p_fan_lease
OWNER=20261022_685512
[ -d "$LEASE" ]
[ "$(cat "$LEASE/owner")" = "$OWNER" ]
[ "$(uci get glfan.globals.temperature)" = 55 ]
( trap '' HUP; sleep 300; sh /root/ethersense/wifi_detection_20261021/cooling_restore.sh "$OWNER" ) > /tmp/ethersense_fs_fan_watchdog_v2.log 2>&1 < /dev/null &
echo RESTORE_WATCHDOG_PID=$!
echo TEMPERATURE_AND_FAN
cat /sys/class/thermal/thermal_zone0/temp /sys/class/thermal/cooling_device0/cur_state
echo RESTORE_WATCHDOG_READY
