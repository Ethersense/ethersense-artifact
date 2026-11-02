$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE 'Desktop\EtherSense'
$key=Join-Path $env:USERPROFILE '.ssh\ethersense_mt3000'
$options=@('-i',$key,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=4','-o','ServerAliveInterval=3','-o','ServerAliveCountMax=2')
Write-Output 'IDENTITY'
whoami
hostname
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' } | Select-Object InterfaceAlias,IPAddress,AddressState | ConvertTo-Json -Compress
Write-Output 'ORCHESTRATORS'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '(?i)-File\s+.*orchestrat' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress
Write-Output 'IPERF_LISTENERS'
Get-NetTCPConnection -State Listen -LocalPort 5201 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Compress
Write-Output 'ROUTER_HEALTH'
& ssh.exe @options root@192.168.8.1 'sh /root/ethersense/bench_protected/es_probe.sh'
if($LASTEXITCODE -ne 0){throw 'Router health SSH failed; no load started'}
Write-Output 'ROUTER_BOOT'
& ssh.exe @options root@192.168.8.1 'cat /proc/sys/kernel/random/boot_id'
Write-Output 'ROUTER_PROCESSES'
& ssh.exe @options root@192.168.8.1 'ps w'
Write-Output 'ROUTER_WIFI'
& ssh.exe @options root@192.168.8.1 'ip -4 addr show dev apcli0'
& ssh.exe @options root@192.168.8.1 'iwinfo apcli0 info'
Write-Output 'TOOLS'
& ssh.exe @options root@192.168.8.1 'ls -l /root/ethersense/bin'
Get-Command iperf3 | Select-Object Source | ConvertTo-Json -Compress
