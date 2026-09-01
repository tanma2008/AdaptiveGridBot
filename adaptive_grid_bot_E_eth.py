"""Bot E - ETH-USDT v4.9 Smart Demo Loop.

Dedicated E bot entry point. Uses the existing ETH v4.9 implementation and
its configured .env.v49 account. Do not mix with BTC Bot B or SOL Bot H.
"""

from eth_adaptive_grid_v049_demo_smart_loop import smart_loop_main


if __name__ == "__main__":
    smart_loop_main()
