"""Bot H - SOL-USDT v4.9 demo entry point.

Uses the existing SOL v4.9 smart reconciliation implementation.
Do not mix with G v4.8 or other bot accounts.
"""

import os
import sys

# H is a continuous demo runner with a fixed 60-second cadence.
os.environ["DEMO_LOOP_INTERVAL"] = "60"
os.environ["SOL_BOT_PREFIX"] = "H49"

from sol_adaptive_grid_v049_demo_smart_loop import smart_loop_main


if __name__ == "__main__":
    # Preserve explicit test modes when invoked directly.
    if "--once" not in sys.argv and "--loop" not in sys.argv:
        sys.argv.append("--loop")
    smart_loop_main()
