# Agent Remote Interface

Stable interface for agent-driven READ operations on Linux `r740`.

## Actions

`status`, `hostname`, `docker`, `disk`, `memory`, `uptime`, `network`, `health`

`health` runs hostname, uptime, disk, memory, and Docker checks as one read-only health check.

## Safety boundary

- The agent interface is read-only.
- Raw shell syntax is not accepted by the interface.
- Do not add write, delete, restart, shutdown, package-install, Docker-control, or bot-start actions without explicit safety review.
- Target: `root@100.105.241.85` over Tailscale.
