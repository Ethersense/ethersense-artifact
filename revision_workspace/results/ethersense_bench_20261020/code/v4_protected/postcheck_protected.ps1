$ErrorActionPreference='Continue'
Write-Output 'HUGO_CLEANUP'
Get-Process iperf3 -ErrorAction SilentlyContinue | Select-Object Id,ProcessName | ConvertTo-Json -Compress
Get-NetTCPConnection -State Listen -LocalPort 5201 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Compress
Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object DisplayName -like 'EtherSense*' | Select-Object Name,DisplayName,Enabled | ConvertTo-Json -Compress
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '(?i)-File\s+.*orchestrate_protected' } | Select-Object ProcessId | ConvertTo-Json -Compress
Write-Output 'ROUTER_CLEANUP'
$commands=@'
cat /proc/sys/kernel/random/boot_id
sh /root/ethersense/bench_protected/es_probe.sh
echo FAN_TARGET
uci -q get glfan.globals.temperature
echo FAN_UNCOMMITTED_DELTA
uci changes glfan
echo FAN_PERSISTENT_SHA256
sha256sum /etc/config/glfan
echo FAN_LEASE
if [ -d /tmp/ethersense_v4p_fan_lease ]; then echo PRESENT; else echo NONE; fi
echo CAPTURE_AND_IPERF_PIDS
pidof hackrf_transfer iperf3 || true
'@
& ssh.exe -i (Join-Path $env:USERPROFILE '.ssh\ethersense_mt3000') -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=4 root@192.168.8.1 $commands
Write-Output ('ROUTER_SSH_EXIT=' + $LASTEXITCODE)
