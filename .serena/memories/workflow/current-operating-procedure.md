ADAPTIVE GRID BOT — NEW WORKFLOW / ORDER OF OPERATIONS

1. Project uses active bot files with naming pattern `adaptive_grid_bot_<BOT>_<SYMBOL>.py`.
2. Current bot map: A=BTC v4.8, B=BTC v4.9, C=BTC v5.1.1, D=ETH v4.8, E=ETH v4.9, F=ETH v5.1.1 (and future bots continue the same naming convention).
3. `adaptive_grid_bot_D_eth.py` is the latest active ETH D work. It is the file to modify/test when working on D.
4. Legacy/versioned files such as `eth_adaptive_grid_v049_demo_smart_loop.py` are reference-only. OLD FILES MUST NOT BE DELETED. Do not modify reference/legacy files unless the user explicitly instructs it.
5. Before changing code: establish the active file and current checkpoint; never infer active status from an old version number or filename alone.
6. Coding workflow: READ/UNDERSTAND -> identify exact symbol/section -> EDIT -> diagnostics/compile -> DRY RUN -> DEMO EXECUTE when explicitly appropriate -> inspect resulting state/logs -> only then declare the change passed.
7. Do not treat syntax/compile success alone as proof of correctness. Runtime behavior and reconciliation state must be tested.
8. For order-manager changes: preserve bot-owned-only operations, never use cancel-all, respect DEMO-only safety gate, and verify KEEP/REPLACE/PLACE/STALE behavior against actual open orders.
9. For grid behavior: preserve a stable grid anchor so small price movements do not cause unnecessary full-grid replacement. Rebuild/replace only when the grid actually needs to move according to the defined strategy.
10. For loops: when a bot is explicitly made into a loop, default interval is 60 seconds minimum unless the user specifies otherwise. Use explicit `--loop` and `--interval` controls; Ctrl+C must stop cleanly; transient loop errors should not kill the loop when loop mode is enabled.
11. Current operational phase: all bots A-F are running in DEMO and the project is in a WAIT/OBSERVE PERFORMANCE phase. Avoid unnecessary code changes while observing results; collect logs/dashboard evidence before modifying strategy.
12. BAT files must call the active bot file. Only change a BAT when the corresponding bot's CLI behavior changes (e.g. D now uses `--execute-demo --loop --interval 60`). Do not change every BAT automatically.
13. Checkpoint discipline: after a significant successful change, record the current state before moving to another bot/task. Keep work ordered and do not jump between active and reference files.
