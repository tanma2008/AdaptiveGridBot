param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('start','status','stop','log')]
    [string]$Action,
    [Parameter(Mandatory=$true)]
    [string]$Script
)

$ErrorActionPreference = 'Stop'
$HostName = '10.4.24.8'
$User = 'root'
$RemoteRoot = '/home/amnat/AdaptiveGridBot'
$Python = "$RemoteRoot/.venv/bin/python"

if ($Script -notmatch '^[A-Za-z0-9_.-]+\.py$') { throw 'BLOCKED: script must be a simple .py filename' }

$RemoteScript = "$RemoteRoot/$Script"
$LogFile = "$RemoteRoot/.run-$([IO.Path]::GetFileNameWithoutExtension($Script)).log"

$bash = @'
set -u
ROOT='__ROOT__'
PYTHON='__PYTHON__'
SCRIPT='__SCRIPT__'
LOGFILE='__LOGFILE__'

find_pids() {
    ps -eo pid=,args= | grep -F -- "$SCRIPT" | grep -v 'grep -F' | awk '{print $1}'
}

case '__ACTION__' in
    start)
        cd "$ROOT" || exit 2
        test -x "$PYTHON" || { echo 'ERROR: venv Python not found'; exit 3; }
        test -f "$SCRIPT" || { echo 'ERROR: script not found'; exit 3; }
        pids=$(find_pids)
        if [ -n "$pids" ]; then
            echo "ALREADY RUNNING PID=$(echo "$pids" | head -n1)"
            exit 0
        fi
        nohup "$PYTHON" "$SCRIPT" >> "$LOGFILE" 2>&1 </dev/null &
        pid=$!
        echo "STARTED PID=$pid"
        echo "LOG=$LOGFILE"
        sleep 1
        if kill -0 "$pid" 2>/dev/null; then
            exit 0
        fi
        echo 'START FAILED'
        tail -n 30 "$LOGFILE" 2>/dev/null || true
        exit 1
        ;;
    status)
        pids=$(find_pids)
        if [ -n "$pids" ]; then
            echo "RUNNING PID=$(echo "$pids" | head -n1)"
            for p in $pids; do ps -p "$p" -o pid,etime,stat,cmd; done
        else
            echo 'NOT RUNNING'
        fi
        echo "LOG=$LOGFILE"
        ;;
    stop)
        pids=$(find_pids)
        if [ -n "$pids" ]; then
            kill $pids 2>/dev/null || true
            echo "STOPPED PID=$pids"
        else
            echo 'NOT RUNNING'
        fi
        ;;
    log)
        if [ -f "$LOGFILE" ]; then
            tail -n 50 "$LOGFILE"
        else
            echo 'NO LOG'
        fi
        ;;
    *)
        echo 'ERROR: invalid action'
        exit 2
        ;;
esac
'@

$bash = $bash.Replace('__ROOT__', $RemoteRoot).Replace('__PYTHON__', $Python).Replace('__SCRIPT__', $RemoteScript).Replace('__LOGFILE__', $LogFile).Replace('__ACTION__', $Action)

# Encode as UTF-8 base64 so PowerShell quoting and Windows CRLF cannot alter the Bash script.
$bytes = [Text.Encoding]::UTF8.GetBytes($bash)
$b64 = [Convert]::ToBase64String($bytes)

Write-Host '========================================'
Write-Host '       REMOTE BOT RUNNER'
Write-Host '========================================'
Write-Host "Host    : $HostName"
Write-Host "Root    : $RemoteRoot"
Write-Host "Python  : $Python"
Write-Host "Action  : $Action"
Write-Host "Script  : $Script"
Write-Host '----------------------------------------'

$b64 | ssh -T "$User@$HostName" 'base64 -d | bash'
$exitCode = $LASTEXITCODE

Write-Host '----------------------------------------'
Write-Host "Exit Code : $exitCode"
Write-Host '========================================'
exit $exitCode

