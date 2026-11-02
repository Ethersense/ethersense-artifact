# Deploy static hackrf tools to GL-MT3000, run hackrf_info, then one 1 s test capture -> pull -> verify -> delete.
# Writes only /root/ethersense (flash, ~1 MB) and /tmp/es on the router. No network/firewall/cron changes.
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'es_common.ps1')
$Status = Join-Path $Base 'logs\deploy_status.txt'
trap { Say ('FAILED: ' + $_.Exception.Message); Set-Content $Status ('FAIL ' + $_.Exception.Message) -Encoding ASCII; exit 1 }
Set-Content $Status 'RUNNING' -Encoding ASCII
# 1. verify kit binaries against shipped SHA256SUMS
$bin = Join-Path $Base 'bin'
foreach ($line in Get-Content (Join-Path $bin 'SHA256SUMS')) {
    $want, $f = $line -split '\s+', 2; $f = Split-Path $f -Leaf
    $got = (Get-FileHash (Join-Path $bin $f) -Algorithm SHA256).Hash.ToLower()
    if ($got -ne $want) { throw "local checksum mismatch: $f" }
    Say "local ok $f $got"
}
# 2. deploy (idempotent)
$r = Rsh 'mkdir -p /root/ethersense/bin /tmp/es && echo OK'; if ($r.code -ne 0) { throw "mkdir: $($r.out)" }
foreach ($f in 'hackrf_info', 'hackrf_transfer') { Scp-To (Join-Path $bin $f) "/root/ethersense/bin/$f" }
Scp-To (Join-Path $Base 'scripts\capture_one.sh') '/root/ethersense/capture_one.sh'
$r = Rsh 'chmod 755 /root/ethersense/bin/* && cd /root/ethersense/bin && sha256sum hackrf_info hackrf_transfer && df -k /overlay | tail -1'
Say ("router sha256/overlay: " + ($r.out -replace "`n", ' | '))
foreach ($line in Get-Content (Join-Path $bin 'SHA256SUMS')) { $want = ($line -split '\s+')[0]; if ($r.out -notmatch $want) { throw 'router checksum mismatch after copy' } }
# 3. hackrf_info
$r = Rsh '/root/ethersense/bin/hackrf_info 2>&1'
Set-Content (Join-Path $Base "logs\hackrf_info_$Stamp.txt") $r.out -Encoding ASCII
Say ("hackrf_info exit=$($r.code): " + ($r.out -replace "`n", ' | '))
if ($r.code -ne 0 -or $r.out -notmatch 'Serial number') { throw 'hackrf_info did not find the HackRF' }
# 4. 1 s test capture (20e6 samples = 40 MB)
$dest = Join-Path $Base 'data\20261019_shorttest'
$m = Capture-Pull 'T1' $dest 20000000
Say ("T1: {0}-{1}s rc={2} bytes={3} mem_kb {4}->{5} load={6}" -f $m.start_epoch, $m.end_epoch, $m.rc, $m.bytes, $m.mem_avail_kb_before, $m.mem_avail_kb_after, $m.loadavg_after)
Get-Content (Join-Path $dest 'T1.log') | Select-Object -Last 8 | ForEach-Object { Say ("transfer: $_") }
$r = Rsh 'ls /tmp/es; df -k /tmp | tail -1'; Say ("router /tmp after: " + ($r.out -replace "`n", ' | '))
Set-Content $Status 'DONE' -Encoding ASCII
Say 'deploy_and_test finished'
