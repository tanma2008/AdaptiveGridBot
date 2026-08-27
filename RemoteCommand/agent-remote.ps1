param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("status", "hostname", "docker", "disk", "memory", "uptime", "network", "health")]
    [string]$Action
)

$ErrorActionPreference = "Stop"
$HostName = "100.105.241.85"
$User = "root"
$Bridge = Join-Path $PSScriptRoot "remote-linux.ps1"

if (-not (Test-Path -LiteralPath $Bridge -PathType Leaf)) {
    throw "RemoteCommand bridge not found: $Bridge"
}

if ($Action -ne "health") {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bridge $Action
    exit $LASTEXITCODE
}

Write-Host "========================================"
Write-Host "       REMOTE HEALTH CHECK - LINUX"
Write-Host "========================================"
Write-Host "Target  : r740 / $HostName"
Write-Host "Mode    : READ-ONLY"
Write-Host "----------------------------------------"

$checks = @(
    @{ Name = "hostname"; Command = "hostname" },
    @{ Name = "uptime";   Command = "uptime" },
    @{ Name = "disk";     Command = "df -h /" },
    @{ Name = "memory";   Command = "free -h" },
    @{ Name = "docker";   Command = "docker ps" }
)

$failed = $false

foreach ($check in $checks) {
    Write-Host "[ $($check.Name) ]"
    & ssh.exe -n "$User@$HostName" $check.Command
    if ($LASTEXITCODE -ne 0) {
        $failed = $true
        Write-Host "Check failed: $($check.Name)"
    }
    Write-Host ""
}

Write-Host "========================================"
if ($failed) {
    Write-Host "Health Check : FAILED"
    exit 1
}
else {
    Write-Host "Health Check : OK"
    exit 0
}
