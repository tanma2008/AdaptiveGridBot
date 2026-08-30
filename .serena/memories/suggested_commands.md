# Windows commands
- Project root: `D:\AdaptiveGridBot`.
- Use PowerShell for project commands.
- Git sync: `git pull --ff-only origin master`.
- Before syncing when local changes may exist: `git status --short --branch`; preserve local work with `git stash push -u -m "..."` rather than destructive reset.
- Run Python entrypoints with `python .\<script>.py` (or the project's `.venv` Python when present).