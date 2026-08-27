# RemoteCommand

Remote read-only command bridge from Windows to Linux `r740` over Tailscale.

Target: `root@100.105.241.85`

## Allowed actions

- `status` — hostname, user, uptime
- `hostname` — hostname
- `docker` — running Docker containers
- `disk` — filesystem usage for `/`
- `memory` — memory usage
- `uptime` — uptime
- `network` — network addresses

## Usage

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\RemoteCommand\remote-linux.ps1 status
powershell.exe -ExecutionPolicy Bypass -File .\RemoteCommand\remote-linux.ps1 docker
```

This layer intentionally does not accept arbitrary shell commands. Write, restart, stop, delete, and other administrative operations remain disabled.
