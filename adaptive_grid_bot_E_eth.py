"""Bot E - ETH-USDT v4.9 Smart Demo Loop.

Dedicated E bot entry point. Uses the existing ETH v4.9 implementation and
its configured .env.v49 account. Do not mix with BTC Bot B or SOL Bot H.
"""

import os
import sys

from eth_adaptive_grid_v049_demo_smart_loop import smart_loop_main


if __name__ == "__main__":
    # Keep the BAT untouched: E always starts in continuous loop mode.
    # Override the shared 30s default with a 60s interval for Bot E.
    if "--once" not in sys.argv and "--loop" not in sys.argv:
        sys.argv.append("--loop")
    # The shared runner reads DEMO_LOOP_INTERVAL from the environment.
    os.environ["DEMO_LOOP_INTERVAL"] = "60"
    smart_loop_main()
