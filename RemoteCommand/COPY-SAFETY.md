# Code Copy Safety

`agent-copy.ps1` copies code from the local `D:\AdaptiveGridBot` project to the Linux sandbox `/opt/adaptivegridbot` over SSH/Tailscale.

Safety boundaries:

- Local source must be inside `D:\AdaptiveGridBot`.
- Remote destination must be relative to `/opt/adaptivegridbot`.
- `..` traversal and absolute destinations are blocked.
- Common secret/credential names (`.env`, SSH private keys, `credentials.json`) are blocked.
- The script creates only the requested destination parent directory.
- It does not delete remote files.
- It does not run copied code.
- It does not control Docker or system services.

Example:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RemoteCommand\agent-copy.ps1 .\grid_engine.py bots\grid_engine.py
```
