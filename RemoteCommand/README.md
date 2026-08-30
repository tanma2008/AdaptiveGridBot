# RemoteCommand

Windows → Linux `r740` remote workflow over SSH key.

Target: `root@10.4.24.8`

Canonical bot workspace: `/home/amnat/AdaptiveGridBot`

## Main interface

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\RemoteCommand\serena-remote.ps1 status
powershell.exe -ExecutionPolicy Bypass -File .\RemoteCommand\serena-remote.ps1 test-write
powershell.exe -ExecutionPolicy Bypass -File .\RemoteCommand\serena-remote.ps1 copy -Source .\adaptive_grid_v048_boss_demo_smart_loop.py -Destination adaptive_grid_v048_boss_demo_smart_loop.py
powershell.exe -ExecutionPolicy Bypass -File .\RemoteCommand\serena-remote.ps1 run-status -Script adaptive_grid_v048_boss_demo_smart_loop.py
powershell.exe -ExecutionPolicy Bypass -File .\RemoteCommand\serena-remote.ps1 run-log -Script adaptive_grid_v048_boss_demo_smart_loop.py
```

## Safety

- SSH uses the configured Windows SSH key.
- Copy is restricted to files inside the local AdaptiveGridBot project.
- Destination is restricted to `/home/amnat/AdaptiveGridBot`.
- Common secret/credential files are blocked.
- Bot start/stop is explicit and only accepts a simple `.py` filename.
- No arbitrary shell command is exposed by the interface.
