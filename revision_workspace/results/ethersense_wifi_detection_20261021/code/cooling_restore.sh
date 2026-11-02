#!/bin/sh
set -eu
LEASE=/tmp/ethersense_v4p_fan_lease
OWNER=${1:-}
case "$OWNER" in ''|*[!0-9_]*) exit 26;; esac
[ -d "$LEASE" ] || { echo NO_FAN_LEASE; exit 0; }
[ "$(cat "$LEASE/owner" 2>/dev/null)" = "$OWNER" ] || { echo NO_OWNED_FAN_LEASE; exit 0; }
OLD=$(cat "$LEASE/original_target")
EXPECTED=$(cat "$LEASE/persistent_sha256")
ACTUAL=$(sha256sum /etc/config/glfan | cut -d' ' -f1)
CURRENT=$(uci -q get glfan.globals.temperature)
if [ "$ACTUAL" != "$EXPECTED" ] || [ "$CURRENT" != 55 ]; then
    echo FAN_CONFIG_CHANGED_EXTERNALLY_NO_OVERWRITE
    exit 24
fi
uci revert glfan.globals.temperature
RESTORED=$(uci -q get glfan.globals.temperature)
[ "$RESTORED" = "$OLD" ] || { echo FAN_RESTORE_MISMATCH; exit 25; }
/etc/init.d/gl_fan restart
rm -f "$LEASE/original_target" "$LEASE/persistent_sha256" "$LEASE/owner"
rmdir "$LEASE"
echo "FAN_TARGET_RESTORED=$RESTORED persistent_config_unchanged=yes"
