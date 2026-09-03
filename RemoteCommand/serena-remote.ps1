param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('status','test-write','copy','run-start','run-status','run-log','run-stop')]
    [string]$Action,

    [string]$Source,
    [string]$Destination,
    [string]$Script
)

$ErrorActionPreference = 'Stop'
$HostName = '10.4.24.8'
$User = 'root'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RemoteRoot = '/home/amnat/AdaptiveGridBot'
$CopyScript = Join-Path $PSScriptRoot 'agent-copy.ps1'
$RunScript = Join-Path $PSScriptRoot 'agent-run.ps1'

Write-Host '========================================'
Write-Host '      SERENA REMOTE - R740'
Write-Host '========================================'
Write-Host "Target  : $User@$HostName"
Write-Host "Root    : $RemoteRoot"
Write-Host "Action  : $Action"
Write-Host '----------------------------------------'

switch ($Action) {
    'status' {
        & ssh.exe -n "$User@$HostName" "hostname && whoami && pwd && test -d '$RemoteRoot' && echo BOT_ROOT_OK"
        exit $LASTEXITCODE
    }

    'test-write' {
        $content = "Serena Remote SSH OK - $HostName`n"
        $bytes = [Text.Encoding]::UTF8.GetBytes($content)
        $b64 = [Convert]::ToBase64String($bytes)
        $cmd = "echo '$b64' | base64 -d > '$RemoteRoot/serena-ssh-test.txt' && chmod 600 '$RemoteRoot/serena-ssh-test.txt' && ls -l '$RemoteRoot/serena-ssh-test.txt'"
        & ssh.exe -n "$User@$HostName" $cmd
        exit $LASTEXITCODE
    }

    'copy' {
        if ([string]::IsNullOrWhiteSpace($Source) -or [string]::IsNullOrWhiteSpace($Destination)) {
            throw 'Source and Destination are required.'
        }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $CopyScript -Source $Source -Destination $Destination
        exit $LASTEXITCODE
    }

    'run-start' { $runAction = 'start' }
    'run-status' { $runAction = 'status' }
    'run-log' { $runAction = 'log' }
    'run-stop' { $runAction = 'stop' }
}

if ($Action -like 'run-*') {
    if ([string]::IsNullOrWhiteSpace($Script)) { throw 'Script is required.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RunScript -Action $runAction -Script $Script
    exit $LASTEXITCODE
}
