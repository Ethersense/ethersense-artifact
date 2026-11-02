$ErrorActionPreference='Continue'
Write-Output 'HUGO_IDENTITY'
whoami
hostname
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' } | Select-Object InterfaceAlias,IPAddress,AddressState | ConvertTo-Json -Compress
Write-Output 'EXISTING_ORCHESTRATORS'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '(?i)-File\s+.*orchestrat' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress
Write-Output 'EXISTING_IPERF'
Get-Process iperf3 -ErrorAction SilentlyContinue | Select-Object Id,ProcessName | ConvertTo-Json -Compress
Get-NetTCPConnection -State Listen -LocalPort 5201 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Compress
Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object DisplayName -like 'EtherSense*' | Select-Object Name,DisplayName,Enabled | ConvertTo-Json -Compress
Write-Output 'LATEST_RUNS'
Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE 'Desktop\EtherSense\data') -Directory -Filter 'wifi_ab_v4*' | Sort-Object LastWriteTime | Select-Object -Last 3 Name,LastWriteTime | ConvertTo-Json -Compress
Write-Output 'ROUTER_HEALTH'
$command=@'
date
uptime
cat /proc/sys/kernel/random/boot_id
grep -E '^MemAvailable|^MemFree' /proc/meminfo
for z in /sys/class/thermal/thermal_zone*; do [ -d "$z" ] || continue; echo "$z"; cat "$z/type" "$z/temp"; done
ps w | grep -E 'hackrf_transfer|iperf3|es_trial|orchestrat' | grep -v grep || true
ip -4 addr show dev apcli0
ip route get 192.168.31.175
ls -l /root/ethersense/bin
ls -l /root/ethersense/bench
logread | grep -iE 'under.?volt|brown.?out|watchdog|thermal|reboot' | tail -15
'@
& ssh.exe -i (Join-Path $env:USERPROFILE '.ssh\ethersense_mt3000') -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=4 root@192.168.8.1 $command
Write-Output ('ROUTER_SSH_EXIT=' + $LASTEXITCODE)
