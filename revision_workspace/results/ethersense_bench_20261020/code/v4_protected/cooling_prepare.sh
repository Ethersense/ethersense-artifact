#!/bin/sh
# Temporary in-RAM UCI delta only. Persistent /etc/config/glfan is not written.
set -eu
LEASE=/tmp/ethersense_v4p_fan_lease
OWNER=${1:-}
case "$OWNER" in ''|*[!0-9_]*) exit 26;; esac
[ -x /etc/init.d/gl_fan ] || { echo FAN_CONTROLLER_UNAVAILABLE; exit 20; }
[ -z "$(uci changes glfan)" ] || { echo EXISTING_FAN_CONFIG_DELTA; exit 21; }
OLD=$(uci -q get glfan.globals.temperature)
case "$OLD" in ''|*[!0-9]*) exit 22;; esac
[ "$OLD" -ge 30 ] && [ "$OLD" -le 90 ] || exit 22
mkdir "$LEASE" || { echo EXISTING_FAN_LEASE; exit 23; }
echo "$OWNER" > "$LEASE/owner"
echo "$OLD" > "$LEASE/original_target"
sha256sum /etc/config/glfan | cut -d' ' -f1 > "$LEASE/persistent_sha256"
uci set glfan.globals.temperature=55
/etc/init.d/gl_fan restart
echo "FAN_TARGET original_c=$OLD temporary_c=55 persistent_config_unchanged=yes"
cat "$LEASE/persistent_sha256"
