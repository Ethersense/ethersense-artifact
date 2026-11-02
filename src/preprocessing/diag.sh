#!/bin/sh
# EtherSense read-only diagnostics: prints information only, changes nothing.
sec(){ echo; echo "=== $1 ==="; }
sec FIRMWARE
cat /etc/openwrt_release 2>&1
echo "glversion: $(cat /etc/glversion 2>/dev/null)"
echo "gl_model: $(cat /proc/gl-hw-info/device_model 2>/dev/null)"
uname -a
sec ARCH
uname -m
grep -m2 -iE 'model name|processor|cpu model|CPU part' /proc/cpuinfo
echo "cores: $(grep -c ^processor /proc/cpuinfo)"
opkg print-architecture 2>&1 | tail -n 4
ls -l /lib/ld-musl* /lib/libc.so* 2>/dev/null
sec USB
for d in /sys/bus/usb/devices/*; do
  [ -f "$d/idVendor" ] || continue
  echo "$(basename "$d") $(cat "$d/idVendor"):$(cat "$d/idProduct") speed=$(cat "$d/speed" 2>/dev/null)Mbps mfr=$(cat "$d/manufacturer" 2>/dev/null) product=$(cat "$d/product" 2>/dev/null) serial=$(cat "$d/serial" 2>/dev/null)"
done
command -v lsusb >/dev/null 2>&1 && lsusb
dmesg 2>/dev/null | grep -iE 'usb [0-9]|hackrf|1d50' | tail -n 12
sec STORAGE
df -k 2>&1
grep -E ' / | /tmp | /overlay | /rom ' /proc/mounts
sec MEMORY
free 2>&1
grep -E 'MemTotal|MemFree|MemAvailable|^Cached|Shmem:' /proc/meminfo
echo "loadavg: $(cat /proc/loadavg)"
sec COMMANDS
for c in flock timeout sha256sum md5sum stat sync nohup nice ionice crond crontab logger ntpd uci opkg scp dropbear sshd lsusb hackrf_info hackrf_transfer python3 tar gzip; do
  p=$(command -v "$c" 2>/dev/null); echo "$c: ${p:-MISSING}"
done
for s in /usr/libexec/sftp-server /usr/lib/sftp-server /usr/libexec/openssh/sftp-server; do [ -e "$s" ] && echo "sftp-server: $s"; done
echo "busybox: $(busybox 2>&1 | head -n 1)"
echo "busybox applets of interest: $(busybox --list 2>/dev/null | grep -xE 'flock|timeout|sha256sum|crond|ntpd' | tr '\n' ' ')"
ls -l /usr/lib/libusb* /lib/libusb* 2>/dev/null
sec TIME
date; date -u; echo "epoch: $(date +%s)"
uptime
uci show system 2>/dev/null | grep -iE 'zonename|timezone|ntp'
pidof ntpd >/dev/null && echo "ntpd: running" || echo "ntpd: NOT running"
logread 2>/dev/null | grep -i ntp | tail -n 5
sec CRON
pidof crond >/dev/null && echo "crond: running" || echo "crond: NOT running"
[ -x /etc/init.d/cron ] && { /etc/init.d/cron enabled && echo "cron: enabled at boot" || echo "cron: NOT enabled at boot"; }
ls -l /etc/crontabs 2>&1
crontab -l 2>&1 | head -n 20
sec SSHD
ps w 2>/dev/null | grep -E '[d]ropbear|[s]shd'
sec END
echo DIAG_DONE