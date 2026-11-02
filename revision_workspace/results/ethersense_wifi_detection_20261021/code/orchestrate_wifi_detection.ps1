# Run ON HUGO. Short isolated trials, no wired stress, stop at the first anomaly.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$root = Join-Path $env:USERPROFILE 'Desktop\EtherSense'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$out = Join-Path $root "data\wifi_detection_$stamp"
New-Item -ItemType Directory -Path $out | Out-Null
$log = Join-Path $out 'orchestrator.log'
$stopFile = Join-Path $out 'STOP_REQUESTED.txt'
$key = Join-Path $env:USERPROFILE '.ssh\ethersense_mt3000'
$sshExe = (Get-Command ssh.exe).Source
$scpExe = (Get-Command scp.exe).Source
$sshOptions = @('-i',$key,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=4','-o','ServerAliveInterval=3','-o','ServerAliveCountMax=2')
$remoteBase = '/root/ethersense/wifi_detection_20261021'
$ruleNames = @()
$poll = $null
$server = $null
$lockStream = $null
$completed = $false
$lastUptime = -1
$fanChanged = $false
function Log([string]$message) {
    $line = (Get-Date -Format o) + ' ' + $message
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
    Write-Host $line
}
function Remote([string]$command) {
    $stderr = Join-Path $out 'last_ssh_stderr.txt'
    $result = @(& $sshExe @sshOptions root@192.168.8.1 $command 2> $stderr)
    if ($LASTEXITCODE -ne 0) { throw "SSH failed ($LASTEXITCODE); no automatic retry" }
    return ($result -join "`n")
}
function Health {
    if (Test-Path -LiteralPath $stopFile) { throw ([IO.File]::ReadAllText($stopFile)) }
    $line = Remote "sh $remoteBase/es_probe.sh"
    $match = [regex]::Match($line, 'uptime_s=(\d+) load1=([\d.]+) memavail_kb=(-?\d+) max_temp_mc=(-?\d+)')
    if (-not $match.Success) { throw 'Invalid health sample; refusing load' }
    $uptime = [int64]$match.Groups[1].Value
    $memory = [int64]$match.Groups[3].Value
    $temperature = [int]$match.Groups[4].Value
    if ($script:lastUptime -ge 0 -and $uptime -lt $script:lastUptime) { throw 'Router uptime decreased; possible reboot' }
    $script:lastUptime = $uptime
    if ($temperature -lt 0) { throw 'Temperature sensor unavailable; refusing load' }
    if ($temperature -ge 70000) { throw "Temperature limit reached: $temperature mC" }
    if ($memory -lt 65536) { throw "Available memory below 64 MiB: $memory KiB" }
    return [pscustomobject]@{ Uptime=$uptime; Temperature=$temperature; Memory=$memory; Raw=$line }
}
function Cooldown([int]$seconds) {
    Log "COOLING seconds=$seconds"
    for ($elapsed=0; $elapsed -lt $seconds; $elapsed+=5) {
        Start-Sleep -Seconds 5
        $sample = Health
    }
    $sample = Health
    if ($sample.Temperature -ge 60000) { throw "Not below 60 C after cooling: $($sample.Temperature) mC; stopping" }
}
function StopServer {
    if ($null -ne $script:server) {
        $script:server.Refresh()
        if (-not $script:server.HasExited) { Stop-Process -Id $script:server.Id -Force -ErrorAction SilentlyContinue }
        $script:server.Dispose()
        $script:server = $null
    }
}
function VerifyFiles([string]$directory) {
    $manifest = Join-Path $directory 'SHA256SUMS'
    if (-not (Test-Path -LiteralPath $manifest)) { throw 'Missing trial checksum manifest' }
    $count = 0
    foreach ($line in (Get-Content -LiteralPath $manifest -Encoding ASCII)) {
        $match = [regex]::Match($line, '^([a-f0-9]{64})\s+\./([A-Za-z0-9_.]+)$')
        if (-not $match.Success) { throw 'Invalid trial checksum entry' }
        $file = Join-Path $directory $match.Groups[2].Value
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'Missing downloaded trial file' }
        $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $match.Groups[1].Value) { throw 'Trial file checksum mismatch; router copy retained' }
        $count++
    }
    if ($count -lt 5) { throw 'Trial manifest is incomplete' }
    return $count
}
function Trial([string]$name,[int]$rate) {
    $sample = Health
    if ($sample.Temperature -ge 60000) { throw "Pre-trial temperature is not below 60 C: $($sample.Temperature)" }
    $destination = Join-Path $out $name
    New-Item -ItemType Directory -Path $destination | Out-Null
    Log "BEGIN $name offered_mbps=$rate $($sample.Raw)"
    if ($rate -gt 0) {
        if (@(Get-NetTCPConnection -State Listen -LocalPort 5201 -ErrorAction SilentlyContinue).Count -gt 0) { throw 'Port 5201 already in use; preserving existing service' }
        $serverLog = Join-Path $destination 'server.json'
        $serverArgs = @('-s','-1','-B',$script:wifiPeer,'-p','5201','-J','--logfile',$serverLog)
        $script:server = Start-Process -FilePath $script:iperfExe -ArgumentList $serverArgs -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 1
        $script:server.Refresh()
        if ($script:server.HasExited) { throw 'One-shot iperf3 server failed to start' }
    }
    $command = "sh $remoteBase/es_wifi_trial.sh $stamp $name $rate $script:wifiPeer"
    $sshArgs = $sshOptions + @('root@192.168.8.1',$command)
    $process = Start-Process -FilePath $sshExe -ArgumentList $sshArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $destination 'ssh_stdout.log') -RedirectStandardError (Join-Path $destination 'ssh_stderr.log')
    # Keep the native handle open before waiting; PS 5.1 can otherwise expose a null ExitCode.
    $null=$process.Handle
    if (-not $process.WaitForExit(40000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $process.Dispose()
        throw 'Trial exceeded host-side 40 s deadline; router watchdog is capped at 25 s'
    }
    $process.Refresh()
    $trialExit = $process.ExitCode
    if ($null -eq $trialExit) { throw 'Native process exit code unavailable; refusing to assume success' }
    $process.Dispose()
    if ($null -ne $script:server) { $null=$script:server.WaitForExit(4000) }
    StopServer
    & $scpExe -O -q -l 100000 -r @sshOptions "root@192.168.8.1:/tmp/ethersense_wifi_detection_$stamp/$name/*" $destination 2> (Join-Path $destination 'scp_stderr.log')
    if ($LASTEXITCODE -ne 0) { throw 'Trial download failed; router files retained; stopping' }
    $verified = VerifyFiles $destination
    $sampleAfter = Health
    if ($trialExit -ne 0 -or (Test-Path -LiteralPath (Join-Path $destination 'guard.txt')) -or -not (Test-Path -LiteralPath (Join-Path $destination 'done'))) { throw "Trial $name incomplete/guarded (exit=$trialExit); stopping without retry" }
    $rawPath=Join-Path $destination 'capture.cs8'
    if ((Get-Item -LiteralPath $rawPath).Length -ne 40000000) { throw 'Capture is not exactly 40 MB' }
    # Only this trial's raw file is removed, after the entire manifest was verified.
    $null=Remote "rm -f /tmp/ethersense_wifi_detection_$stamp/$name/capture.cs8"
    Log "END $name ok files_verified=$verified $($sampleAfter.Raw)"
    Cooldown 60
}
try {
    $lockPath = Join-Path $root 'logs\v4_protected.lock'
    $lockStream = [IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $others = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '(?i)-File\s+.*orchestrat' })
    if ($others.Count -gt 0) { throw 'Another EtherSense orchestrator exists; refusing concurrent test' }
    $script:iperfExe = (Get-Command iperf3).Source
    $wifiAddresses = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.31.*' -and $_.AddressState -eq 'Preferred' })
    if ($wifiAddresses.Count -ne 1) { throw 'Expected exactly one HUGO upstream Wi-Fi IPv4 address; refusing to change network' }
    $script:wifiPeer = $wifiAddresses[0].IPAddress
    $routerAddresses = Remote 'ip -4 addr show dev apcli0'
    $addressMatch = [regex]::Match($routerAddresses,'inet\s+(192\.168\.31\.\d+)/')
    if (-not $addressMatch.Success) { throw 'Router upstream Wi-Fi address unavailable' }
    $routerWifi = $addressMatch.Groups[1].Value
    $initial = Health
    [ordered]@{ experiment='wifi_load_signature_probe'; start=(Get-Date -Format o); wifi_peer=$script:wifiPeer; router_wifi=$routerWifi; target_state='pending_physical_confirmation'; external_lna_power='not_remotely_verified'; radio_role='2.4 GHz STA via upstream AP'; offered_udp_mbps=@(0,5,25); udp_payload_bytes=1200; udp_seconds=10; capture_samples=20000000; capture_fs_hz=20000000; capture_fc_hz=20000000; capture_start_after_seconds=4; lna_gain_db=16; vga_gain_db=4; internal_amp=0; format='signed int8 IQ'; independent_reference='REF_idle'; formal_repeats_per_load=3; rest_seconds=60; start_below_celsius=60; stop_at_celsius=70; watchdog_seconds=25; fan_target_celsius=55; fan_setting_storage='temporary UCI delta, restored in finally'; no_retry=$true; wired_stress=$false; classifier_scope='predefined spectral-template probe, not full multiclass classifier'; order=@('B1_idle','B1_udp5','B1_udp25','B2_udp5','B2_udp25','B2_idle','B3_udp25','B3_idle','B3_udp5') } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'design.json') -Encoding UTF8
    Log "START initial=$($initial.Raw) peer=$script:wifiPeer router=$routerWifi"
    # Mark intent first so finally also restores a partially completed setup.
    $fanChanged=$true
    $fanResult=Remote "sh $remoteBase/cooling_prepare.sh $stamp"
    Set-Content -LiteralPath (Join-Path $out 'fan_prepare.txt') -Value $fanResult -Encoding UTF8
    Log $fanResult
    foreach ($protocol in @('TCP','UDP')) {
        $ruleName = "EtherSense-wifidet-$stamp-$protocol"
        New-NetFirewallRule -Name $ruleName -DisplayName $ruleName -Direction Inbound -Action Allow -Program $script:iperfExe -Protocol $protocol -LocalAddress $script:wifiPeer -LocalPort 5201 -RemoteAddress $routerWifi -Profile Any | Out-Null
        $ruleNames += $ruleName
    }
    $healthPath = Join-Path $out 'health.log'
    $poll = Start-Job -ArgumentList $healthPath,$stopFile,$key,$remoteBase -ScriptBlock {
        param($healthPath,$stopFile,$key,$remoteBase)
        $last = -1
        $options = @('-i',$key,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=3','-o','ServerAliveInterval=2','-o','ServerAliveCountMax=2')
        while ($true) {
            $line = @(& ssh.exe @options root@192.168.8.1 "sh $remoteBase/es_probe.sh" 2>$null) -join ' '
            $code = $LASTEXITCODE
            Add-Content -LiteralPath $healthPath -Value ((Get-Date -Format o) + ' ' + $line) -Encoding UTF8
            $match = [regex]::Match($line,'uptime_s=(\d+).*memavail_kb=(-?\d+) max_temp_mc=(-?\d+)')
            $reason = ''
            if ($code -ne 0) { $reason='Health poll lost SSH; stopping at first failure' }
            elseif (-not $match.Success) { $reason='Invalid health poll' }
            else {
                $uptime=[int64]$match.Groups[1].Value; $memory=[int64]$match.Groups[2].Value; $temperature=[int]$match.Groups[3].Value
                if ($last -ge 0 -and $uptime -lt $last) { $reason='Uptime decreased: possible reboot' }
                elseif ($temperature -lt 0 -or $temperature -ge 70000) { $reason='Missing sensor or temperature limit reached' }
                elseif ($memory -lt 65536) { $reason='Memory guard reached' }
                $last=$uptime
            }
            if ($reason) { Set-Content -LiteralPath $stopFile -Value $reason -Encoding UTF8; break }
            Start-Sleep -Seconds 5
        }
    }
    Cooldown 60
    Trial 'REF_idle' 0
    New-Item -ItemType File -Path (Join-Path $out 'REFERENCE_READY') | Out-Null
    Log 'WAIT_REFERENCE_TEMPLATE no traffic; fixed template must be stored before formal measurements'
    $ack=Join-Path $out 'TEMPLATE_READY.json'
    for ($elapsed=0; $elapsed -lt 240 -and -not (Test-Path -LiteralPath $ack); $elapsed+=5) {
        Start-Sleep -Seconds 5
        $null=Health
    }
    if (-not (Test-Path -LiteralPath $ack)) { throw 'Reference template not approved by the predefined validity check within 240 seconds' }
    $template=Get-Content -LiteralPath $ack -Raw -Encoding UTF8 | ConvertFrom-Json
    $referenceHash=(Get-FileHash -LiteralPath (Join-Path $out 'REF_idle\capture.cs8') -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($template.reference_sha256 -ne $referenceHash -or $template.selected_peaks -lt 4) { throw 'Reference template identity or minimum-feature validity check failed' }
    Log "TEMPLATE_FIXED sha256=$referenceHash peaks=$($template.selected_peaks)"
    $trials=@(@('B1_idle',0),@('B1_udp5',5),@('B1_udp25',25),@('B2_udp5',5),@('B2_udp25',25),@('B2_idle',0),@('B3_udp25',25),@('B3_idle',0),@('B3_udp5',5))
    foreach ($trial in $trials) { Trial ([string]$trial[0]) ([int]$trial[1]) }
    $completed=$true
    Log 'COMPLETE independent reference and 3 rotated repeats at each of 0, 5, 25 Mbit/s UDP offered load'
} catch {
    Log ('STOP ' + $_.Exception.Message)
    Set-Content -LiteralPath (Join-Path $out 'STOPPED.txt') -Value $_.Exception.Message -Encoding UTF8
} finally {
    StopServer
    if ($null -ne $poll) { Stop-Job $poll -ErrorAction SilentlyContinue; Remove-Job $poll -Force -ErrorAction SilentlyContinue }
    foreach ($ruleName in $ruleNames) { Remove-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue }
    $remaining = @($ruleNames | ForEach-Object { Get-NetFirewallRule -Name $_ -ErrorAction SilentlyContinue }).Count
    if ($fanChanged) {
        try {
            $restored=Remote "sh $remoteBase/cooling_restore.sh $stamp"
            Set-Content -LiteralPath (Join-Path $out 'fan_restore.txt') -Value $restored -Encoding UTF8
            Log $restored
        } catch { Log ('FAN_RESTORE_FAILED ' + $_.Exception.Message) }
    }
    Log "CLEANUP completed=$completed own_firewall_rules_left=$remaining"
    if ($null -ne $lockStream) { $lockStream.Dispose() }
    if ($completed) { New-Item -ItemType File -Path (Join-Path $out 'ALL_DONE') | Out-Null }
    # Raw captures remain in their verified per-trial directories; no duplicate 400 MB zip.
}
