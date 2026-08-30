#!/usr/bin/env python3
from __future__ import annotations
import os, platform, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
TARGETS = {
    "BTC": ["adaptive_grid_v049_demo_smart_loop.py", "adaptive_grid_v048_boss_demo_smart_loop.py"],
    "ETH": ["eth_adaptive_grid_v049_demo_smart_loop.py"],
    "SOL": ["sol_adaptive_grid_v049_demo_smart_loop.py"],
    "BOSS": ["adaptive_grid_v049_boss_demo_smart_loop.py"],
}
def run(command):
    try: return subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc: return f"<command failed: {exc}>"
def main():
    print("="*72); print(" ADAPTIVE GRID BOT — LOCAL READ-ONLY MONITOR"); print("="*72)
    print(f"OS       : {platform.platform()}"); print(f"Python   : {sys.version.split()[0]}"); print(f"Project  : {ROOT}")
    print("\n=== PROJECT BOT FILES ===")
    for name, files in TARGETS.items():
        found=[f for f in files if (ROOT/f).exists()]
        print(f"{name:5}: " + (", ".join(found) if found else "NOT FOUND"))
    print("\n=== RUNNING BOT PROCESSES (READ ONLY) ===")
    if os.name == "nt":
        cmd="powershell -NoProfile -Command \"Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|pythonw' -and $_.CommandLine -match 'adaptive_grid|eth_adaptive|sol_adaptive|BOSS' } | Select-Object ProcessId,Name,CommandLine | Format-Table -AutoSize\""
    else:
        cmd="ps -eo pid,lstart,etime,args | grep -E 'python.*(adaptive_grid|eth_adaptive|sol_adaptive)' | grep -v grep"
    print(run(cmd) or "NO ADAPTIVE GRID BOT PROCESS FOUND")
    print("\n=== GIT ===")
    print("Branch   :", run("git branch --show-current")); print("Commit   :", run("git log -1 --oneline"))
    dirty=run("git status --short"); print("WORKTREE : CLEAN" if not dirty else "WORKTREE : MODIFIED\n"+dirty)
    print("\nSAFETY: READ ONLY — no order placement/cancellation.")
if __name__ == "__main__": main()
