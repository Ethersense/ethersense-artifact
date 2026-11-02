#!/bin/sh
# Router side: one fixed-parameter capture into /tmp/es. Usage: capture_one.sh NAME [NSAMPLES]
# Writes NAME.cs8 (signed 8-bit interleaved IQ) only if complete; otherwise leaves NAME.cs8.part and exits non-zero.
# Never deletes anything except its own stale .part of the same name.
B=/root/ethersense; D=/tmp/es; NAME=$1; NS=${2:-20000000}
FC=20000000; FS=20000000; LNA=16; VGA=4; AMP=0
mkdir -p "$D"; cd "$D" || exit 9
exec 9>"$D/.lock"; flock -n 9 || { echo "ERR_BUSY"; exit 4; }
[ -e "$NAME.cs8" ] && { echo "ERR_EXISTS $NAME.cs8 (not pulled yet)"; exit 5; }
rm -f "$NAME.cs8.part"
NEED_KB=$((NS*2/1024 + 30720))
AVAIL_KB=$(df -k /tmp | awk 'NR==2{print $4}')
MEM0=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
[ "$AVAIL_KB" -gt "$NEED_KB" ] || { echo "ERR_SPACE tmp_avail_kb=$AVAIL_KB need_kb=$NEED_KB"; exit 3; }
T0=$(date +%Y-%m-%dT%H:%M:%S%z); E0=$(date +%s)
timeout 60 "$B/bin/hackrf_transfer" -r "$NAME.cs8.part" -f $FC -s $FS -l $LNA -g $VGA -a $AMP -n $NS > "$NAME.log" 2>&1
RC=$?
E1=$(date +%s); MEMMIN=$(awk '/MemAvailable/{print $2}' /proc/meminfo); LOAD=$(cut -d' ' -f1-3 /proc/loadavg)
SZ=$(wc -c < "$NAME.cs8.part" 2>/dev/null || echo 0)
OK=0; [ "$RC" -eq 0 ] && [ "$SZ" -eq $((NS*2)) ] && OK=1
if [ $OK -eq 1 ]; then mv "$NAME.cs8.part" "$NAME.cs8"; SHA=$(sha256sum "$NAME.cs8" | cut -d' ' -f1); else SHA=""; fi
cat > "$NAME.json" <<EOF
{"name":"$NAME","start_local":"$T0","start_epoch":$E0,"end_epoch":$E1,"fc_hz":$FC,"fs_hz":$FS,"lna_db":$LNA,"vga_db":$VGA,"amp":$AMP,"n_samples":$NS,"format":"cs8 interleaved I,Q signed int8","bytes":$SZ,"expected_bytes":$((NS*2)),"rc":$RC,"complete":$OK,"sha256":"$SHA","tmp_avail_kb_before":$AVAIL_KB,"mem_avail_kb_before":$MEM0,"mem_avail_kb_after":$MEMMIN,"loadavg_after":"$LOAD","hackrf_serial":"$(cat /sys/bus/usb/devices/1-1/serial 2>/dev/null)"}
EOF
echo "CAPTURE name=$NAME rc=$RC bytes=$SZ complete=$OK sha256=$SHA"
[ $OK -eq 1 ] || exit 2
