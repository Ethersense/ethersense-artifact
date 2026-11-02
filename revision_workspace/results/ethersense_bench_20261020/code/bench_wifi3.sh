#!/bin/sh
# Round 3 (external LNA state as of 21:40, after the user noticed it was unpowered earlier) of the Wi-Fi A/B (same path and conditions as bench_wifi.sh); each iperf3 run is retried up to 3 times
# because the Windows iperf3 server occasionally resets the control connection (seen in both conditions in round 1).
OUT=/tmp/es_bench3; BIN=/root/ethersense/bin; WIFI=192.168.31.175; WIRED=192.168.8.170
mkdir -p $OUT; cd $OUT || exit 1
exec >run.log 2>&1
echo "START $(date +%s) $(date)"; iwinfo apcli0 info | grep -E 'Bit Rate|Signal'
cpu() { head -1 /proc/stat; }
ip3() {  # ip3 <outfile> <iperf3 args...>
  f=$1; shift; n=1
  while [ $n -le 3 ]; do
    iperf3 "$@" -J >$f; grep -q '"error"' $f || { echo "ok $f try=$n"; return 0; }
    echo "retry $f try=$n: $(grep '"error"' $f)"; n=$((n+1)); sleep 3
  done
}
start_cap() { $BIN/hackrf_transfer -r /dev/null -f 20000000 -s 20000000 -l 16 -g 4 -a 0 >"$1.hackrf.txt" 2>&1 & echo $! >hackrf.pid; sleep 3; }
stop_cap() { kill -INT "$(cat hackrf.pid)" 2>/dev/null; sleep 2; kill "$(cat hackrf.pid)" 2>/dev/null; rm -f hackrf.pid; }
for rep in 7 8 9; do
  if [ $rep = 8 ]; then order="idle capture"; else order="capture idle"; fi
  for cond in $order; do
    t="r${rep}_${cond}"; echo "== $t $(date +%s)"
    [ $cond = capture ] && start_cap $t
    cpu >$t.cpu0
    ip3 $t.wifi_tcp_rx.json -c $WIFI -t 20 -O 2 -R; sleep 2
    ip3 $t.wifi_tcp_tx.json -c $WIFI -t 20 -O 2; sleep 2
    ip3 $t.wifi_udp50.json -c $WIFI -u -b 50M -t 10; sleep 2
    ip3 $t.wired_tcp_tx.json -c $WIRED -t 10 -O 1
    cpu >$t.cpu1; iwinfo apcli0 info | grep -E 'Bit Rate|Signal' >$t.link.txt
    [ $cond = capture ] && stop_cap
    sleep 3
  done
done
echo "END $(date +%s) $(date)"; touch DONE
