param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$HostName = "10.4.24.8"
$User = "root"
$RemoteRoot = "/home/amnat/AdaptiveGridBot"

# Resolve and constrain source to the local AdaptiveGridBot project.
$sourceItem = Get-Item -LiteralPath $Source -ErrorAction Stop
$sourceFull = $sourceItem.FullName
$rootWithSlash = $ProjectRoot.TrimEnd('\') + '\'
if (-not ($sourceFull.Equals($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase) -or $sourceFull.StartsWith($rootWithSlash, [System.StringComparison]::OrdinalIgnoreCase))) {
    throw "BLOCKED: source must be inside $ProjectRoot"
}

# Destination is always relative to the remote sandbox.
if ([System.IO.Path]::IsPathRooted($Destination) -or $Destination -match '(^|[\\/])\.\.([\\/]|$)') {
    throw "BLOCKED: destination must be relative to $RemoteRoot"
}
$relative = $Destination -replace '\\', '/'
if ($relative -match '(^|/)\.(/|$)' -or $relative.StartsWith('/')) {
    throw "BLOCKED: invalid destination path"
}

# Never copy common secrets/credentials through this interface.
$blockedNames = @('.env', '.env.local', '.env.production', 'id_rsa', 'id_ed25519', 'credentials.json')
foreach ($part in ($sourceFull -split '[\\/]')) {
    if ($blockedNames -contains $part) {
        throw "BLOCKED: secret/credential file is not allowed"
    }
}

$leafName = $sourceItem.Name
$remotePath = "$RemoteRoot/$relative"
if ([string]::IsNullOrWhiteSpace($relative)) {
    $remotePath = "$RemoteRoot/$leafName"
}

Write-Host "========================================"
Write-Host "        AGENT CODE COPY - LINUX"
Write-Host "========================================"
Write-Host "Source  : $sourceFull"
Write-Host "Target  : ${User}@${HostName}:$remotePath"
Write-Host "Mode    : SANDBOXED WRITE"
Write-Host "----------------------------------------"

# Create only the requested destination directory, then copy via SCP.
$parent = Split-Path -Path $remotePath -Parent
ssh -n "$User@$HostName" "mkdir -p '$parent'"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($sourceItem.PSIsContainer) {
    scp -r -- "$sourceFull" "$User@$HostName`:$remotePath"
}
else {
    scp -- "$sourceFull" "$User@$HostName`:$remotePath"
}

$exitCode = $LASTEXITCODE
Write-Host "----------------------------------------"
Write-Host "Exit Code : $exitCode"
Write-Host "========================================"
exit $exitCode




