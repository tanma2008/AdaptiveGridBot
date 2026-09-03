param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("status", "hostname", "docker", "disk", "memory", "uptime", "network")]
    [string]$Action
)

$HostName = "10.4.24.8"
$User = "root"

$Commands = @{
    status   = "hostname && whoami && uptime"
    hostname = "hostname"
    docker   = "docker ps"
    disk     = "df -h /"
    memory   = "free -h"
    uptime   = "uptime"
    network  = "ip addr"
}

$Command = $Commands[$Action]

Write-Host "========================================"
Write-Host "       REMOTE COMMAND - LINUX"
Write-Host "========================================"
Write-Host "Host    : $HostName"
Write-Host "User    : $User"
Write-Host "Mode    : READ-ONLY"
Write-Host "Action  : $Action"
Write-Host "----------------------------------------"

ssh "$User@$HostName" $Command
$exitCode = $LASTEXITCODE

Write-Host "----------------------------------------"
Write-Host "Exit Code : $exitCode"
Write-Host "========================================"

exit $exitCode

