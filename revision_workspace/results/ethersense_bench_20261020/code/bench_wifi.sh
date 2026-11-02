#!/bin/sh
# EtherSense C3/C11: does HackRF 20 MS/s capture on the GL-MT3000 change its Wi-Fi throughput?
# Wi-Fi path: MT3000 radio (apcli0, 2.4 GHz ch1) -> upstream AP -> MEASUREMENT_PC WLAN 192.168.31.175.
# Wired control: MT3000 br-lan -> MEASUREMENT_PC Ethernet 192.168.8.170. Conditions alternate per repetition.
OUT=/tmp/es_bench; BIN=/root/ethersense/bin; WIFI=192.168.31.175; WIRED=192.168.8.170
mkdir -p $OUT; cd $OUT || exit 1
exec >run.log 2>&1
echo "START $(date +%s) $(date)"; uptime; iwinfo apcli0 info | grep -E 'Bit Rate|Signal|Channel'
cpu() { head -1 /proc/stat; }
start_cap() {
  $BIN/hackrf_transfer -r /dev/null -f 20000000 -s 20000000 -l 16 -g 4 -a 0 >"$1.hackrf.txt" 2>&1 &
  echo $! >hackrf.pid; sleep 3
}
stop_cap() {
  kill -INT "$(cat hackrf.pid)" 2>/dev/null; sleep 2; kill "$(cat hackrf.pid)" 2>/dev/null; rm -f hackrf.pid
}
for rep in 1 2 3; do
  if [ $rep = 2 ]; then order="capture idle"; else order="idle capture"; fi
  for cond in $order; do
    t="r${rep}_${cond}"; echo "== $t $(date +%s)"
    [ $cond = capture ] && start_cap $t
    cpu >$t.cpu0; cat /proc/loadavg >$t.load0
    iperf3 -c $WIFI -t 20 -O 2 -J >$t.wifi_tcp_tx.json
    iperf3 -c $WIFI -t 20 -O 2 -R -J >$t.wifi_tcp_rx.json
    iperf3 -c $WIFI -u -b 50M -t 10 -J >$t.wifi_udp50.json
    ping -c 10 $WIFI >$t.wifi_ping.txt
    iperf3 -c $WIRED -t 10 -O 1 -J >$t.wired_tcp_tx.json
    cpu >$t.cpu1; cat /proc/loadavg >$t.load1; free >$t.mem
    iwinfo apcli0 info | grep -E 'Bit Rate|Signal' >$t.link.txt
    [ $cond = capture ] && stop_cap
    sleep 3
  done
done
echo "END $(date +%s) $(date)"
touch DONE
