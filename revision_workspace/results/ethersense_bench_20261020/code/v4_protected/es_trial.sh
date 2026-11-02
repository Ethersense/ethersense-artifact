#!/bin/sh
# One short trial; no retries, wired traffic, or unbounded capture.
# Usage: es_trial.sh NAME CAP(0|1) hold|tx|rx|udp HUGO_WIFI_IP
set -u
NAME=${1:-}; CAP=${2:-}; TEST=${3:-}; PEER=${4:-}
case "$NAME" in ''|*[!A-Za-z0-9_]*) echo INVALID_NAME; exit 2;; esac
[ ${#NAME} -le 64 ] || exit 2
case "$CAP" in 0|1) ;; *) exit 2;; esac
case "$TEST" in hold|tx|rx|udp) ;; *) exit 2;; esac
case "$PEER" in 192.168.31.*) ;; *) echo INVALID_PEER; exit 2;; esac
case "$PEER" in *[!0-9.]*) exit 2;; esac
BASE=/root/ethersense
PARENT=/tmp/ethersense_v4_protected
mkdir -p "$PARENT" /tmp/es || exit 3
exec 9>/tmp/es/.lock
flock -n 9 || { echo OTHER_CAPTURE_ACTIVE; exit 4; }
D=$PARENT/$NAME
mkdir "$D" || { echo TRIAL_ALREADY_EXISTS; exit 5; }
cd "$D" || exit 3
HP=; IP=; GP=; RESULT=INCOMPLETE
live() {
    [ -n "$1" ] && [ -r "/proc/$1/stat" ] || return 1
    state=$(awk '{print $3}' "/proc/$1/stat" 2>/dev/null)
    [ "$state" != Z ] && [ "$state" != X ]
}
stop_one() {
    [ -n "$1" ] || return 0
    if live "$1"; then kill -INT "$1" 2>/dev/null || :; fi
    i=0
    while live "$1" && [ "$i" -lt 2 ]; do sleep 1; i=$((i+1)); done
    if live "$1"; then kill -TERM "$1" 2>/dev/null || :; fi
    if live "$1"; then sleep 1; fi
    if live "$1"; then kill -KILL "$1" 2>/dev/null || :; fi
}
finish() {
    rc=$?
    trap - 0 INT TERM HUP
    if [ -n "$GP" ]; then kill "$GP" 2>/dev/null || :; wait "$GP" 2>/dev/null || :; fi
    stop_one "$IP"
    stop_one "$HP"
    [ -z "$IP" ] || wait "$IP" 2>/dev/null || :
    [ -z "$HP" ] || wait "$HP" 2>/dev/null || :
    sh "$BASE/bench_protected/es_probe.sh" > health_after.txt
    head -1 /proc/stat > cpu_after.txt
    iwinfo apcli0 info > link_after.txt 2>&1 || :
    [ ! -f guard.txt ] || RESULT=GUARD_STOP
    echo "$RESULT" > result.txt
    if [ "$RESULT" = OK ]; then echo ok > done; fi
    (for file in ./*; do [ "$file" = './SHA256SUMS' ] || sha256sum "$file"; done) > SHA256SUMS
    echo "TRIAL_END name=$NAME result=$RESULT rc=$rc"
    exit "$rc"
}
trap finish 0
trap 'exit 130' INT
trap 'exit 143' TERM HUP
sh "$BASE/bench_protected/es_probe.sh" > health_before.txt
TEMP=$(sed -n 's/.*max_temp_mc=\([-0-9]*\).*/\1/p' health_before.txt)
MEM=$(sed -n 's/.*memavail_kb=\([-0-9]*\).*/\1/p' health_before.txt)
if [ -z "$TEMP" ] || [ "$TEMP" -lt 0 ] || [ "$TEMP" -ge 60000 ]; then
    echo "PRECHECK_TEMPERATURE $TEMP" > guard.txt; exit 6
fi
if [ -z "$MEM" ] || [ "$MEM" -lt 65536 ]; then
    echo "PRECHECK_MEMORY $MEM" > guard.txt; exit 6
fi
ip route get "$PEER" > route.txt
grep -q 'dev apcli0' route.txt || { echo WRONG_WIFI_ROUTE > guard.txt; exit 6; }
head -1 /proc/stat > cpu_before.txt
iwinfo apcli0 info > link_before.txt 2>&1 || :
printf 'name=%s\ncap=%s\ntest=%s\npeer=%s\nfs_hz=20000000\nfc_hz=20000000\nlna_db=16\nvga_db=4\namp=0\nudp_offered_mbps=20\n' "$NAME" "$CAP" "$TEST" "$PEER" > metadata.txt
# Independent watchdog stops only the two PIDs belonging to THIS trial.
(
    start=$(cut -d. -f1 /proc/uptime)
    while :; do
        line=$(sh "$BASE/bench_protected/es_probe.sh")
        echo "$line" >> health_during.txt
        temp=$(echo "$line" | sed -n 's/.*max_temp_mc=\([-0-9]*\).*/\1/p')
        mem=$(echo "$line" | sed -n 's/.*memavail_kb=\([-0-9]*\).*/\1/p')
        now=$(cut -d. -f1 /proc/uptime)
        reason=
        if [ -z "$temp" ] || [ "$temp" -lt 0 ]; then reason=SENSOR_MISSING
        elif [ "$temp" -ge 70000 ]; then reason=TEMPERATURE_LIMIT
        elif [ -z "$mem" ] || [ "$mem" -lt 65536 ]; then reason=MEMORY_LIMIT
        elif [ $((now-start)) -ge 25 ]; then reason=TIME_LIMIT
        fi
        if [ -n "$reason" ]; then
            echo "$reason $line" > guard.txt
            for file in hackrf.pid iperf.pid; do
                [ -f "$file" ] || continue
                pid=$(cat "$file")
                kill -INT "$pid" 2>/dev/null || :
            done
            sleep 1
            for file in hackrf.pid iperf.pid; do
                [ -f "$file" ] || continue
                pid=$(cat "$file")
                kill -TERM "$pid" 2>/dev/null || :
            done
            sleep 1
            for file in hackrf.pid iperf.pid; do
                [ -f "$file" ] || continue
                pid=$(cat "$file")
                kill -KILL "$pid" 2>/dev/null || :
            done
            exit 0
        fi
        sleep 1
    done
) &
GP=$!
if [ "$CAP" = 1 ]; then
    # n is an additional hardware-side duration cap, even if SSH disappears.
    "$BASE/bin/hackrf_transfer" -r /dev/null -f 20000000 -s 20000000 -l 16 -g 4 -a 0 -n 400000000 > hackrf.txt 2>&1 &
    HP=$!; echo "$HP" > hackrf.pid
    sleep 2
    live "$HP" || { echo CAPTURE_EARLY_EXIT > guard.txt; exit 7; }
fi
if [ "$TEST" = hold ]; then
    sleep 6
else
    case "$TEST" in
        tx)  set -- -t 10 -O 2;;
        rx)  set -- -t 10 -O 2 -R;;
        udp) set -- -u -b 20M -t 8;;
    esac
    iperf3 -c "$PEER" -p 5201 "$@" -J > iperf.json 2> iperf_stderr.txt &
    IP=$!; echo "$IP" > iperf.pid
    wait "$IP"; IRC=$?
    IP=; rm -f iperf.pid
    echo "$IRC" > iperf_rc.txt
    [ "$IRC" -eq 0 ] && ! grep -q '"error"' iperf.json || exit 8
fi
[ ! -f guard.txt ] || exit 9
if [ "$CAP" = 1 ]; then
    live "$HP" || { echo CAPTURE_EARLY_EXIT > guard.txt; exit 7; }
fi
RESULT=OK
exit 0
