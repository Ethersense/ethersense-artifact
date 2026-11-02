# Capture a group of N consecutive 1 s recordings, each pulled+verified before the next.
# Usage: capture_group.ps1 -Label env|target [-Count 3]
param([Parameter(Mandatory = $true)][ValidatePattern('^[a-z]+$')][string]$Label, [int]$Count = 3)
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'es_common.ps1')
$Status = Join-Path $Base "logs\group_${Label}_status.txt"
trap { Say ('FAILED: ' + $_.Exception.Message); Set-Content $Status ('FAIL ' + $_.Exception.Message) -Encoding ASCII; exit 1 }
$dest = Join-Path $Base 'data\20261019_ab'
for ($i = 1; $i -le $Count; $i++) {
    $name = "${Label}$i"
    if (Test-Path (Join-Path $dest "$name.cs8")) { throw "$name already exists locally; refusing to overwrite" }
    Set-Content $Status "RUNNING $name" -Encoding ASCII
    $m = Capture-Pull $name $dest 20000000
    Say ("{0}: start={1} rc={2} bytes={3} mem_kb {4}->{5}" -f $name, $m.start_local, $m.rc, $m.bytes, $m.mem_avail_kb_before, $m.mem_avail_kb_after)
}
Set-Content $Status "DONE $Count" -Encoding ASCII
Say "group $Label finished"
