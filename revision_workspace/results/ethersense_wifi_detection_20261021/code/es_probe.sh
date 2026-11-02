#!/bin/sh
# Read-only health sample. Missing/invalid sensors remain explicit.
UP=$(cut -d. -f1 /proc/uptime)
LOAD=$(cut -d' ' -f1 /proc/loadavg)
MEM=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
MAX=-1
for f in /sys/class/thermal/thermal_zone*/temp; do
    [ -r "$f" ] || continue
    v=$(cat "$f" 2>/dev/null)
    case "$v" in ''|*[!0-9]*) continue;; esac
    [ "$v" -gt 0 ] && [ "$v" -lt 150000 ] || continue
    [ "$v" -gt "$MAX" ] && MAX=$v
done
PWM=$(cat /sys/class/thermal/cooling_device0/cur_state 2>/dev/null || echo unknown)
RPM=$(cat /sys/class/hwmon/hwmon0/fan1_input 2>/dev/null || echo unknown)
echo "uptime_s=$UP load1=$LOAD memavail_kb=${MEM:--1} max_temp_mc=$MAX fan_pwm=$PWM fan_rpm=$RPM"
