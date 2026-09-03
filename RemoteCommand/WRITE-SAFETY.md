# WRITE Sandbox Safety

The write interface is deliberately separate from the read-only interface.

## Remote sandbox

`/opt/adaptivegridbot`

Only relative paths under this directory are accepted. Absolute paths and `..` traversal are blocked. Protected path segments such as `.ssh`, `.git`, `etc`, `root`, `proc`, `sys`, and `dev` are blocked.

## Actions

- `ensure-workdir` — creates `/opt/adaptivegridbot` with mode 700.
- `list-workdir` — lists files under the sandbox (max depth 2).
- `write-text` — writes UTF-8 text to a relative file under the sandbox; maximum 1 MiB.

## Intentionally disabled

No arbitrary shell command, delete, move, chmod outside the sandbox, service restart, Docker control, package installation, reboot, or bot execution is exposed.

## First deployment

Run `ensure-workdir` manually once and verify the result before using `write-text`.
