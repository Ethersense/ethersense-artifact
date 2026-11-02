#!/bin/sh
# K2 online-overhead benchmark on GL-MT3000 (read-mostly; writes only /tmp/es and /root/ethersense).
# Prints sections; each line prefixed for easy parsing. Fixed RF settings as in the A/B test.
B=/root/ethersense; D=/tmp/es; mkdir -p $D; cd $D || exit 9
exec 9>"$D/.lock"; flock -n 9 || { echo "ERR_BUSY"; exit 4; }
FC=20000000; LNA=16; VGA=4
cpu(){ awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5+$6}' /proc/stat; }   # total idle
mem(){ awk '/MemAvailable/{print $2}' /proc/meminfo; }
# sample CPU busy % and min MemAvailable every 1 s (busybox sleep is integer-only) while PID $1 runs
watch(){ set -- $(cpu); t0=$1; i0=$2; mmin=$(mem); while [ -e /proc/$W ] && [ "$(cut -d' ' -f3 /proc/$W/stat 2>/dev/null)" != Z ]; do sleep 1; m=$(mem); [ $m -lt $mmin ] && mmin=$m; done
         set -- $(cpu); echo "cpu_busy_pct=$(awk -v a=$t0 -v b=$i0 -v c=$1 -v d=$2 'BEGIN{printf "%.1f",100*(1-(d-b)/(c-a))}') memavail_min_kb=$mmin"; }

echo "== IDLE (HackRF attached, not streaming), 5 s"
set -- $(cpu); t0=$1; i0=$2; sleep 5; set -- $(cpu)
echo "IDLE cpu_busy_pct=$(awk -v a=$t0 -v b=$i0 -v c=$1 -v d=$2 'BEGIN{printf "%.1f",100*(1-(d-b)/(c-a))}') memavail_kb=$(mem) load=$(cut -d' ' -f1-3 /proc/loadavg)"

echo "== FILE: es_psd on a 1 s / 20 MSPS capture already in RAM"
$B/bin/hackrf_transfer -r $D/bench.cs8 -f $FC -s 20000000 -l $LNA -g $VGA -a 0 -n 20000000 >/dev/null 2>&1
echo "FILEBYTES $(wc -c < $D/bench.cs8)"
for N in 1024 4096 16384; do echo "FILE N=$N $($B/bin/es_psd -N $N -r 1.0 < $D/bench.cs8 | tail -1)"; done
rm -f $D/bench.cs8

for FS in 20000000 10000000 8000000 4000000 2000000; do
  NS=$((FS*10))
  echo "== LIVE fs=$FS 10 s: hackrf_transfer | es_psd -N 4096"
  ( $B/bin/hackrf_transfer -r - -f $FC -s $FS -l $LNA -g $VGA -a 0 -n $NS 2>$D/ht_$FS.log | $B/bin/es_psd -N 4096 -r 1.0 -s $FS > $D/psd_$FS.txt ) &
  W=$!; echo "LIVE fs=$FS $(watch)"
  echo "LIVE fs=$FS es_psd: $(tail -1 $D/psd_$FS.txt)"
  echo "LIVE fs=$FS reports: $(grep -vc '^#' $D/psd_$FS.txt)"
  grep -E 'MiB|dropped|overflow|underflow|Couldn|error' $D/ht_$FS.log | head -n 12 | sed "s/^/LIVE fs=$FS ht: /"
  rm -f $D/ht_$FS.log $D/psd_$FS.txt
done

echo "== DUTY: capture 1 s to RAM, then process (the A/B workflow on the AP)"
T0=$(cut -d" " -f1 /proc/uptime)
$B/bin/hackrf_transfer -r $D/duty.cs8 -f $FC -s 20000000 -l $LNA -g $VGA -a 0 -n 20000000 >/dev/null 2>&1
T1=$(cut -d" " -f1 /proc/uptime)
$B/bin/es_psd -N 4096 -r 1.0 < $D/duty.cs8 > $D/duty_psd.txt
T2=$(cut -d" " -f1 /proc/uptime)
echo "DUTY uptime_s t0=$T0 t1=$T1 t2=$T2 capture_s=$(awk -v a=$T0 -v b=$T1 'BEGIN{print b-a}') process_s=$(awk -v a=$T1 -v b=$T2 'BEGIN{print b-a}') result: $(grep -v '^#' $D/duty_psd.txt | head -1 | cut -d' ' -f1-5)"
rm -f $D/duty.cs8 $D/duty_psd.txt
echo "== END memavail_kb=$(mem) tmp_kb=$(df -k /tmp | awk 'NR==2{print $4}')"
echo BENCH_DONE
