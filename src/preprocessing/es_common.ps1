# Shared helpers for EtherSense router scripts (Windows side). ASCII only.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$Base   = Join-Path $env:USERPROFILE 'Desktop\EtherSense'
$Key    = Join-Path $env:USERPROFILE '.ssh\ethersense_mt3000'
$Router = 'root@192.168.8.1'
$SshOpt = @('-i', $Key, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes')
$Stamp  = Get-Date -Format 'yyyyMMdd_HHmmss'
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'logs') | Out-Null
if (-not (Get-Variable -Name LogFile -Scope Script -ErrorAction SilentlyContinue)) { $script:LogFile = Join-Path $Base "logs\run_$Stamp.log" }
function Say([string]$m) { $l = "[{0}] {1}" -f (Get-Date -Format 's'), $m; Write-Host $l; Add-Content -Path $script:LogFile -Value $l -Encoding ASCII }
function Rsh([string]$cmd) {
    $ErrorActionPreference = 'Continue'   # native stderr must not become a terminating error
    $out = & ssh.exe @SshOpt $Router $cmd 2>&1
    $code = $LASTEXITCODE
    return @{ code = $code; out = (($out | ForEach-Object { "$_" }) -join "`n") }
}
function Scp-From([string]$remote, [string]$local) {
    $ErrorActionPreference = 'Continue'
    & scp.exe -O -q @SshOpt ($Router + ':' + $remote) $local 2>&1 | ForEach-Object { Say ("scp: $_") }
    if ($LASTEXITCODE -ne 0) { throw "scp from $remote failed ($LASTEXITCODE)" }
}
function Scp-To([string]$local, [string]$remote) {
    $ErrorActionPreference = 'Continue'
    & scp.exe -O -q @SshOpt $local ($Router + ':' + $remote) 2>&1 | ForEach-Object { Say ("scp: $_") }
    if ($LASTEXITCODE -ne 0) { throw "scp to $remote failed ($LASTEXITCODE)" }
}
# Capture one file on the router, pull it, verify sha256 locally, and only then delete the router copy.
function Capture-Pull([string]$name, [string]$destDir, [int]$nSamples) {
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $r = Rsh ("sh /root/ethersense/capture_one.sh $name $nSamples")
    Say ("router: " + ($r.out -replace "`n", ' | '))
    foreach ($ext in 'json', 'log') { try { Scp-From "/tmp/es/$name.$ext" (Join-Path $destDir "$name.$ext") } catch { Say "note: $($_.Exception.Message)" } }
    if ($r.code -ne 0) { throw "capture $name failed on router (exit $($r.code)); data left in /tmp/es for inspection" }
    $meta = Get-Content (Join-Path $destDir "$name.json") -Raw | ConvertFrom-Json
    $dst = Join-Path $destDir "$name.cs8"
    Scp-From "/tmp/es/$name.cs8" $dst
    $h = (Get-FileHash $dst -Algorithm SHA256).Hash.ToLower()
    $sz = (Get-Item $dst).Length
    if ($h -ne $meta.sha256 -or $sz -ne $meta.expected_bytes) { throw "verify FAILED for $name (local $h / $sz vs router $($meta.sha256) / $($meta.expected_bytes)); router copy kept" }
    $d = Rsh ("rm -f /tmp/es/$name.cs8 /tmp/es/$name.json /tmp/es/$name.log && echo DELETED")
    Say ("$name verified sha256=$h bytes=$sz; router copy: " + $d.out)
    return $meta
}
