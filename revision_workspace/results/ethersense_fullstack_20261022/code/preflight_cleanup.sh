#!/bin/sh
set -eu
echo RESTORE_OWN_FAN
sh /root/ethersense/wifi_detection_20261021/cooling_restore.sh 20261022_685512
echo FINAL_FAN_TARGET
uci get glfan.globals.temperature
echo PERSISTENT_FAN_HASH
sha256sum /etc/config/glfan
echo FINAL_HEALTH
sh /root/ethersense/wifi_detection_20261021/es_probe.sh
cat /proc/sys/kernel/random/boot_id
echo ACTIVE_CAPTURE_PROCESS
pidof hackrf_transfer || true
echo OWN_TEMP_SCRIPT_CLEANUP
rm -f /tmp/ethersense_fs_891d2e543c721a4c.sh
echo PREFLIGHT_FINISHED_NO_FORMAL_TRIAL
