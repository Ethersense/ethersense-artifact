#!/bin/sh
# One 1 s record per isolated trial. No network configuration is changed.
set -u
BASE=/root/ethersense/wifi_detection_20261021
RUN=${1:-}; NAME=${2:-}; RATE=${3:-}; PEER=${4:-}
case "$RUN" in ''|*[!0-9_]*) exit 2;; esac
case "$NAME" in ''|*[!A-Za-z0-9_]*) exit 2;; esac
case "$RATE" in 0|5|25) :;; *) exit 2;; esac
case "$PEER" in ''|*[!0-9.]*) exit 2;; esac
OUT=/tmp/ethersense_wifi_detection_$RUN/$NAME
[ ! -e "$OUT" ] || { echo TRIAL_ALREADY_EXISTS; exit 3; }
mkdir -p "$OUT" || exit 3
cd "$OUT" || exit 3
BOOT=$(cat /proc/sys/kernel/random/boot_id)
UP0=$(cut -d. -f1 /proc/uptime)
RESULT=FAILED; HP=; IP=; GP=
live() { [ -n "$1" ] && [ -r "/proc/$1/stat" ] && [ "$(awk '{print $3}' /proc/$1/stat)" != Z ]; }
stop_pid() {
    pid=$1
    live "$pid" || return 0
    kill -INT "$pid" 2>/dev/null || :
    sleep 1
    live "$pid" && kill -TERM "$pid" 2>/dev/null || :
}
cleanup() {
    trap - EXIT INT TERM HUP
    [ -n "$GP" ] && kill "$GP" 2>/dev/null || :
    stop_pid "$HP"; stop_pid "$IP"
    sh "$BASE/es_probe.sh" >> health.log
    date -u > end_utc.txt
    echo "$RESULT" > result.txt
    [ "$RESULT" = OK ] && [ ! -f guard.txt ] && touch done
    sha256sum ./* > SHA256SUMS
}
trap cleanup EXIT
trap 'RESULT=INTERRUPTED; exit 13' INT TERM HUP
date -u > start_utc.txt
printf 'run=%s trial=%s offered_mbps=%s payload_bytes=1200 fc_hz=20000000 fs_hz=20000000 complex_samples=20000000 format=cs8\n' "$RUN" "$NAME" "$RATE" > settings.txt
echo "$BOOT" > boot_id.txt
sh "$BASE/es_probe.sh" > health.log
TEMP=$(sed -n 's/.*max_temp_mc=\([0-9]*\).*/\1/p' health.log)
MEM=$(sed -n 's/.*memavail_kb=\([0-9]*\).*/\1/p' health.log)
[ -n "$TEMP" ] && [ "$TEMP" -lt 60000 ] || { echo PRE_TRIAL_TEMPERATURE > guard.txt; exit 4; }
[ -n "$MEM" ] && [ "$MEM" -ge 131072 ] || { echo PRE_TRIAL_MEMORY > guard.txt; exit 4; }
(
    while :; do
        LINE=$(sh "$BASE/es_probe.sh"); echo "$LINE" >> health.log
        T=$(echo "$LINE" | sed -n 's/.*max_temp_mc=\([0-9]*\).*/\1/p')
        M=$(echo "$LINE" | sed -n 's/.*memavail_kb=\([0-9]*\).*/\1/p')
        NOW=$(cut -d. -f1 /proc/uptime); REASON=
        [ -n "$T" ] && [ "$T" -lt 70000 ] || REASON=TEMPERATURE_LIMIT
        [ -n "$M" ] && [ "$M" -ge 65536 ] || REASON=MEMORY_LIMIT
        [ "$((NOW-UP0))" -lt 25 ] || REASON=TIME_LIMIT
        [ "$(cat /proc/sys/kernel/random/boot_id)" = "$BOOT" ] || REASON=BOOT_CHANGED
        if [ -n "$REASON" ]; then
            echo "$REASON $LINE" > guard.txt
            for F in hackrf.pid iperf.pid; do
                [ -f "$F" ] || continue
                P=$(cat "$F"); kill -INT "$P" 2>/dev/null || :
            done
            sleep 1
            for F in hackrf.pid iperf.pid; do
                [ -f "$F" ] || continue
                P=$(cat "$F"); kill -TERM "$P" 2>/dev/null || :
            done
            sleep 1
            for F in hackrf.pid iperf.pid; do
                [ -f "$F" ] || continue
                P=$(cat "$F"); kill -KILL "$P" 2>/dev/null || :
            done
            exit
        fi
        sleep 1
    done
) &
GP=$!
iwinfo apcli0 info > wifi_before.txt 2>&1
cat /proc/stat > cpu_before.txt
cat /proc/uptime > iperf_start_uptime.txt
if [ "$RATE" -gt 0 ]; then
    iperf3 -c "$PEER" -p 5201 -u -b "${RATE}M" -l 1200 -t 10 -i 1 -J > iperf.json 2> iperf_stderr.txt &
    IP=$!; echo "$IP" > iperf.pid
    sleep 4
    live "$IP" || { echo IPERF_EARLY_EXIT > guard.txt; exit 5; }
else
    sleep 4
fi
cat /proc/uptime > capture_start_uptime.txt
cat /sys/class/net/apcli0/statistics/tx_packets > tx_packets_before.txt
"/root/ethersense/bin/hackrf_transfer" -r capture.cs8 -f 20000000 -s 20000000 -l 16 -g 4 -a 0 -n 20000000 > capture.log 2>&1 &
HP=$!; echo "$HP" > hackrf.pid
wait "$HP"; HRC=$?
HP=; rm -f hackrf.pid
echo "$HRC" > capture_rc.txt
cat /proc/uptime > capture_end_uptime.txt
cat /sys/class/net/apcli0/statistics/tx_packets > tx_packets_after.txt
[ "$HRC" -eq 0 ] || exit 6
[ "$(wc -c < capture.cs8)" -eq 40000000 ] || { echo CAPTURE_LENGTH_MISMATCH > guard.txt; exit 6; }
if [ "$RATE" -gt 0 ]; then
    wait "$IP"; IRC=$?
    IP=; rm -f iperf.pid
    echo "$IRC" > iperf_rc.txt
    [ "$IRC" -eq 0 ] && ! grep -q '"error"' iperf.json || exit 7
else
    sleep 5
fi
cat /proc/stat > cpu_after.txt
iwinfo apcli0 info > wifi_after.txt 2>&1
[ ! -f guard.txt ] || exit 8
RESULT=OK
exit 0
