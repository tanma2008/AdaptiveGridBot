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
    parser = argparse.ArgumentParser(description="Adaptive Grid Bot v4.9 BOSS")
    parser.add_argument("--dry-run", action="store_true", help="Run all three bots without submitting or cancelling orders")
    args = parser.parse_args()

    if os.getenv("OKX_FLAG") != "1":
        raise RuntimeError("ABORTED: v4.9 Boss only permits OKX DEMO (OKX_FLAG=1).")

    print("=" * 78)
    print("ADAPTIVE GRID BOT v4.9 BOSS")
    print("B / v4.9 + E / ETH v4.9 + H / SOL v4.9")
    print("OKX DEMO - THREE BOTS / ONE MACHINE")
    print(f"Execution : {'DRY RUN' if args.dry_run else 'DEMO ORDERS'}")
    print("=" * 78)

    processes = []
    for name, script in BOTS:
        command = [sys.executable, str(ROOT / script), "--once"]
        if args.dry_run:
            command.append("--dry-run")
        print(f"[START] {name} -> {script}")
        processes.append((name, subprocess.Popen(command, cwd=ROOT)))

    failed = False
    for name, process in processes:
        code = process.wait()
        print(f"[STOP]  {name} -> exit {code}")
        failed |= code != 0

    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
