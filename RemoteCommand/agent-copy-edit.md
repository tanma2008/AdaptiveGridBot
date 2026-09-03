# PC → Linux Code Copy / Edit

Target sandbox: `/opt/adaptivegridbot`

Supported workflow:

1. Copy a selected project file from `D:\AdaptiveGridBot` to the server sandbox.
2. Agent/Serena may edit the local project copy before copying it again.
3. Copy operations never delete the destination tree.
4. Secrets such as `.env`, private keys, and credential files must not be copied.
5. Server-side editing is limited to the sandbox; system paths are out of scope.
6. Code is not automatically executed by copy/edit operations.

Recommended F workflow:

`edit → inspect → copy → verify → run → status → log → stop`
