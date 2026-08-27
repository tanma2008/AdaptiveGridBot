param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("ensure-workdir", "list-workdir", "write-text")]
    [string]$Action,

    [string]$RelativePath,
    [string]$Content
)

$ErrorActionPreference = "Stop"
$HostName = "100.105.241.85"
$User = "root"
$WorkRoot = "/opt/adaptivegridbot"

function Assert-SafeRelativePath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "RelativePath is required."
    }

    $p = $Path.Replace('\', '/')
    if ($p.StartsWith('/') -or $p.Contains('..') -or $p.Contains("`0")) {
        throw "Blocked: path must be relative and cannot contain '..' or an absolute path."
    }

    if ($p -match '(^|/)(\.ssh|\.git|proc|sys|dev|etc|root|var)(/|$)') {
        throw "Blocked: protected path segment."
    }

    return $p
}

Write-Host "========================================"
Write-Host "      REMOTE WRITE SANDBOX"
Write-Host "========================================"
Write-Host "Host    : $HostName"
Write-Host "Root    : $WorkRoot"
Write-Host "Mode    : SANDBOXED WRITE"
Write-Host "Action  : $Action"
Write-Host "----------------------------------------"

switch ($Action) {
    "ensure-workdir" {
        # This is the only administrative bootstrap action. It creates the dedicated sandbox.
        ssh -n "$User@$HostName" "mkdir -p $WorkRoot && chmod 700 $WorkRoot"
        exit $LASTEXITCODE
    }

    "list-workdir" {
        ssh -n "$User@$HostName" "find $WorkRoot -maxdepth 2 -type f -printf '%p\n' 2>/dev/null | sort"
        exit $LASTEXITCODE
    }

    "write-text" {
        $safe = Assert-SafeRelativePath $RelativePath
        if ($null -eq $Content) {
            throw "Content is required."
        }

        if ($Content.Length -gt 1048576) {
            throw "Blocked: content exceeds 1 MiB."
        }

        # Encode content locally as base64; only the resulting data is sent to the sandbox path.
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Content)
        $b64 = [Convert]::ToBase64String($bytes)
        $remotePath = "$WorkRoot/$safe"
        $parent = ($remotePath -replace '/[^/]+$','')

        $bootstrap = "mkdir -p '$parent' && chmod 700 '$parent'"
        & ssh -n "$User@$HostName" $bootstrap
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        $command = "echo '$b64' | base64 -d > '$remotePath' && chmod 600 '$remotePath'"
        & ssh -n "$User@$HostName" $command
        exit $LASTEXITCODE
    }
}
