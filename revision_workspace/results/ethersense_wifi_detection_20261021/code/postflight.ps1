$ErrorActionPreference='Stop'
$key=Join-Path $env:USERPROFILE '.ssh\ethersense_mt3000'
$options=@('-i',$key,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=4')
Write-Output 'ROUTER_FINAL_STATE'
& ssh.exe @options root@192.168.8.1 'sh /root/ethersense/wifi_detection_20261021/es_probe.sh; cat /proc/sys/kernel/random/boot_id; uci get glfan.globals.temperature; uci changes glfan; test ! -d /tmp/ethersense_v4p_fan_lease && echo NO_FAN_LEASE; pidof hackrf_transfer; pidof iperf3; sha256sum /etc/config/glfan; echo END_STATE'
if ($LASTEXITCODE -ne 0) { throw 'Final SSH state query failed' }
Write-Output 'OWN_FIREWALL_RULES'
@(Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'EtherSense-wifidet-*' }).Count
Write-Output 'IPERF_LISTENERS'
@(Get-NetTCPConnection -State Listen -LocalPort 5201 -ErrorAction SilentlyContinue).Count
Write-Output 'RUNNER_PROCESSES'
@(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '(?i)-File\s+.*orchestrate_wifi_detection' }).Count
