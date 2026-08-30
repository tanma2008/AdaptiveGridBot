"""Adaptive Grid Bot v4.9 Boss runner.

Runs the three symbol-specific v4.9 demo smart loops together:
B / v4.9 (BTC), E / ETH v4.9, H / SOL v4.9.

The symbol implementations remain separate so their constants, order managers,
and persistent grid state cannot collide. This file is the single launcher.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BOTS = [
    ("B / v4.9", "adaptive_grid_v049_demo_smart_loop.py"),
    ("E / ETH v4.9", "eth_adaptive_grid_v049_demo_smart_loop.py"),
    ("H / SOL v4.9", "sol_adaptive_grid_v049_demo_smart_loop.py"),
]


def main():
    parser = argparse.ArgumentParser(description="Adaptive Grid Bot v4.9 Boss - BTC/ETH/SOL")
    parser.add_argument("--once", action="store_true", help="Run one cycle per bot")
    parser.add_argument("--loop", action="store_true", help="Repeat cycles every 30 seconds")
    parser.add_argument("--dry-run", action="store_true", help="Never submit or cancel orders")
    args = parser.parse_args()

    if os.getenv("OKX_FLAG") != "1":
        raise RuntimeError("ABORTED: v4.9 Boss only permits OKX DEMO (OKX_FLAG=1).")
    if args.dry_run:
        raise RuntimeError("ABORTED: BTC B / v4.9 does not expose a Boss-compatible --dry-run mode.")

    print("=" * 78)
    print("       ADAPTIVE GRID BOT v4.9 BOSS")
    print("       B / v4.9 + E / ETH v4.9 + H / SOL v4.9")
    print("       OKX DEMO - THREE BOTS / ONE MACHINE")
    print("=" * 78)
    print("Execution      : DRY RUN" if args.dry_run else "Execution      : DEMO ORDERS")
    print("Safety         : DEMO flag required; no cancel-all")
    print()

    processes = []
    for name, script in BOTS:
        if args.once and name == "B / v4.9":
            command = [
                sys.executable,
                "-c",
                "from adaptive_grid_v049_demo_smart_loop import run_once; run_once()",
            ]
        else:
            command = [sys.executable, str(ROOT / script)]
            if args.once:
                command.append("--once")
            if args.dry_run:
                command.append("--dry-run")

        print(f"[START] {name} -> {script}")
        processes.append((name, subprocess.Popen(command, cwd=ROOT)))

    failed = False
    try:
        for name, process in processes:
            return_code = process.wait()
            print(f"[STOP]  {name} -> exit {return_code}")
            if return_code != 0:
                failed = True
    except KeyboardInterrupt:
        print("\n[BOSS] Stop requested; stopping all v4.9 bots...")
        for _, process in processes:
            if process.poll() is None:
                process.terminate()
        for _, process in processes:
            process.wait()
        raise SystemExit(130)

    if args.loop and not failed:
        import time
        while True:
            time.sleep(30)
            processes = []
            for name, script in BOTS:
                print(f"[START] {name} -  {name} - {return_code}", flush=True)
                if return_code != 0:
                    raise SystemExit(1)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
