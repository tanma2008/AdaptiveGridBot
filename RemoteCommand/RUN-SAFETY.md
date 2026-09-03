# Remote Bot Runner Safety

The runner supports a controlled long-running Python process under `/opt/adaptivegridbot`.

## Actions

- `start` — starts the selected Python script with `nohup`, detached from SSH, logging to `.run-<name>.log` and recording its PID in `.run-<name>.pid`.
- `status` — checks whether the recorded PID is alive.
- `stop` — stops only the recorded PID for the selected script.

## Boundaries

- Script must be a relative `.py` path.
- Script must resolve under `/opt/adaptivegridbot`.
- `..`, absolute paths, and Windows path separators are rejected.
- No arbitrary shell command is accepted.
- No Docker control, systemd control, reboot, or package installation is exposed.
- The runner does not copy code; use `agent-copy.ps1` first.

## Example

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RemoteCommand\agent-run.ps1 start grid_engine.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RemoteCommand\agent-run.ps1 status grid_engine.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RemoteCommand\agent-run.ps1 stop grid_engine.py
```
