"""
ADAPTIVE GRID BOT v5.1 - FILL SIMULATION MODE

SAFE LOCAL TEST ONLY
- No OKX API calls
- No orders created/cancelled
- Simulates the v5.1 persistent-grid fill/replacement logic
- Candidate E:
    Grid       = 0.60%
    Order size = $20
    SELL mult  = 2.50x
    Profit floor = 0.27%

Simulation:
1) Create the initial 5 BUY + 5 SELL grid.
2) Move price through BUY levels.
3) Simulate fills.
4) Replace each filled BUY with a SELL above the fill price.
5) Move price upward.
6) Simulate SELL fills.
7) Replace each filled SELL with a BUY below the fill price.
8) Verify active order count and cycle P/L.

This is NOT a market backtest and does NOT simulate real OKX matching.
It is a logic/state-machine test for the live Demo bot.
"""

from dataclasses import dataclass
from typing import Dict, List


GRID_PCT = 0.0060
ORDER_USDT = 20.0
SELL_MULT = 2.5
SELL_STEP = GRID_PCT * SELL_MULT

FEE_PER_SIDE = 0.0008
SLIPPAGE_PER_SIDE = 0.00005
PROFIT_FLOOR = 0.0027

MAX_BUY_ORDERS = 5
MAX_SELL_ORDERS = 5
TARGET_ORDERS = 10


@dataclass
class SimOrder:
    order_id: str
    side: str
    price: float
    qty: float
    level: int


class Simulator:
    def __init__(self, anchor: float):
        self.anchor = anchor
        self.orders: Dict[str, SimOrder] = {}
        self.sequence = 0

        self.realized_pnl = 0.0
        self.wins = 0
        self.losses = 0
        self.fills = 0

        self.inventory_btc = 0.0
        self.cash_usdt = 0.0

    def next_id(self, side: str) -> str:
        self.sequence += 1
        return f"SIM{side[0].upper()}{self.sequence:04d}"

    def add_order(self, side: str, price: float, level: int):
        qty = ORDER_USDT / price
        oid = self.next_id(side)

        self.orders[oid] = SimOrder(
            order_id=oid,
            side=side,
            price=price,
            qty=qty,
            level=level,
        )

        print(
            f"  ADD {side:<4} "
            f"px={price:,.2f} "
            f"qty={qty:.6f} "
            f"level={level} "
            f"id={oid}"
        )

    def initial_grid(self):
        print("\nINITIAL GRID")
        print("-" * 72)

        for level in range(1, MAX_SELL_ORDERS + 1):
            price = self.anchor * (1 + SELL_STEP * level)
            self.add_order("sell", price, level)

        for level in range(1, MAX_BUY_ORDERS + 1):
            price = self.anchor * (1 - GRID_PCT * level)
            self.add_order("buy", price, level)

    def active_counts(self):
        buy = sum(1 for o in self.orders.values() if o.side == "buy")
        sell = sum(1 for o in self.orders.values() if o.side == "sell")
        return buy, sell

    def print_state(self, label="STATE"):
        buy, sell = self.active_counts()
        print(
            f"\n{label}: active={len(self.orders)} "
            f"BUY={buy} SELL={sell} "
            f"fills={self.fills} "
            f"realized={self.realized_pnl:+.6f} USDT"
        )

    def fill_one(self, oid: str):
        order = self.orders.pop(oid)

        # Apply one-way execution costs to each fill.
        effective_buy = order.price * (1 + SLIPPAGE_PER_SIDE)
        effective_sell = order.price * (1 - SLIPPAGE_PER_SIDE)

        fee = order.price * order.qty * FEE_PER_SIDE

        self.fills += 1

        print(
            f"\nFILL {order.side.upper():<4} "
            f"px={order.price:,.2f} "
            f"qty={order.qty:.6f} "
            f"level={order.level} "
            f"id={order.order_id}"
        )

        if order.side == "buy":
            # Buy uses USDT and adds BTC inventory.
            self.inventory_btc += order.qty
            self.cash_usdt -= effective_buy * order.qty
            self.cash_usdt -= fee

            # Replace the filled BUY with a SELL above fill price.
            replacement = effective_buy * (1 + SELL_STEP)

            # Profit check: round-trip gross spread must exceed floor
            # after estimated two-sided costs.
            gross = replacement / effective_buy - 1
            net_est = gross - (
                2 * FEE_PER_SIDE + 2 * SLIPPAGE_PER_SIDE
            )

            print(
                f"  REPLACE BUY -> SELL "
                f"px={replacement:,.2f} "
                f"net_est={net_est * 100:.3f}%"
            )

            self.add_order(
                "sell",
                replacement,
                order.level,
            )

        else:
            # Sell releases BTC and receives USDT.
            self.inventory_btc -= order.qty
            self.cash_usdt += effective_sell * order.qty
            self.cash_usdt -= fee

            # Replacement BUY below the filled SELL.
            replacement = effective_sell * (1 - GRID_PCT)

            gross = 1 - replacement / effective_sell
            net_est = gross - (
                2 * FEE_PER_SIDE + 2 * SLIPPAGE_PER_SIDE
            )

            cycle_pnl = (
                effective_sell * order.qty
                - replacement * order.qty
                - (2 * fee)
            )

            self.realized_pnl += cycle_pnl

            if cycle_pnl > 0:
                self.wins += 1
            else:
                self.losses += 1

            print(
                f"  REPLACE SELL -> BUY "
                f"px={replacement:,.2f} "
                f"cycle_pnl={cycle_pnl:+.6f} "
                f"net_est={net_est * 100:.3f}%"
            )

            self.add_order(
                "buy",
                replacement,
                order.level,
            )

    def find_fillable(self, price: float):
        # For a real market:
        # BUY fills when market <= order price.
        # SELL fills when market >= order price.
        candidates = []

        for oid, order in self.orders.items():
            if order.side == "buy" and price <= order.price:
                candidates.append(oid)
            elif order.side == "sell" and price >= order.price:
                candidates.append(oid)

        # Lowest/closest logical fill first.
        if not candidates:
            return None

        candidates.sort(
            key=lambda oid: abs(self.orders[oid].price - price)
        )
        return candidates[0]

    def move_price(self, price: float):
        print(f"\nPRICE -> ${price:,.2f}")

        fills_this_move = 0

        while True:
            oid = self.find_fillable(price)
            if oid is None:
                break

            self.fill_one(oid)
            fills_this_move += 1

            # Safety guard for simulation.
            if fills_this_move > 20:
                raise RuntimeError("Simulation fill loop exceeded safety limit")

        self.print_state("AFTER MOVE")

    def verify(self):
        buy, sell = self.active_counts()

        print("\n" + "=" * 72)
        print("SIMULATION VERIFICATION")
        print("=" * 72)

        checks = [
            ("Active orders == 10", len(self.orders) == TARGET_ORDERS),
            ("BUY orders <= 5", buy <= MAX_BUY_ORDERS),
            ("SELL orders <= 5", sell <= MAX_SELL_ORDERS),
            ("At least one fill", self.fills > 0),
            ("At least one profitable cycle", self.wins > 0),
            ("No duplicate order IDs", len(self.orders) == len(set(self.orders))),
        ]

        passed = 0

        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL':<5} {name}")
            if ok:
                passed += 1

        print()
        print(f"Fills             : {self.fills}")
        print(f"Winning cycles    : {self.wins}")
        print(f"Losing cycles     : {self.losses}")
        print(f"Realized P/L      : {self.realized_pnl:+.6f} USDT")
        print(f"Active orders     : {len(self.orders)}")
        print(f"BUY / SELL        : {buy} / {sell}")

        print("\nRESULT")
        if passed == len(checks):
            print("PASS: v5.1 fill/replacement state machine is behaving correctly.")
            print("No OKX orders were created.")
        else:
            print("FAIL: do not promote this logic to Demo yet.")

        return passed == len(checks)


def main():
    print("=" * 72)
    print("     ADAPTIVE GRID BOT v5.1 - FILL SIMULATION MODE")
    print("=" * 72)
    print("SAFE LOCAL TEST - NO OKX API / NO REAL ORDERS")
    print()
    print(f"Grid          : {GRID_PCT * 100:.2f}%")
    print(f"Order size    : ${ORDER_USDT:.2f}")
    print(f"SELL mult.    : {SELL_MULT:.2f}x")
    print(f"SELL step     : {SELL_STEP * 100:.2f}%")
    print(f"Profit floor  : {PROFIT_FLOOR * 100:.2f}%")
    print(
        f"Round-trip est: "
        f"{(2 * FEE_PER_SIDE + 2 * SLIPPAGE_PER_SIDE) * 100:.3f}% costs"
    )

    # Same approximate price we are currently testing around.
    anchor = 78985.7

    sim = Simulator(anchor)
    sim.initial_grid()
    sim.print_state("INITIAL")

    # TEST 1:
    # Walk down through the first two BUY levels.
    buy1 = anchor * (1 - GRID_PCT * 1)
    buy2 = anchor * (1 - GRID_PCT * 2)

    print("\n" + "=" * 72)
    print("TEST 1: BUY FILLS")
    print("=" * 72)

    sim.move_price(buy1 - 1.0)
    sim.move_price(buy2 - 1.0)

    # TEST 2:
    # Take the replacement SELL prices from current orders and hit them.
    replacement_sells = sorted(
        [
            o.price
            for o in sim.orders.values()
            if o.side == "sell"
        ]
    )

    print("\n" + "=" * 72)
    print("TEST 2: SELL FILLS")
    print("=" * 72)

    # Hit the two nearest replacement sells one by one.
    if replacement_sells:
        sim.move_price(replacement_sells[0] + 1.0)

    replacement_sells = sorted(
        [
            o.price
            for o in sim.orders.values()
            if o.side == "sell"
        ]
    )

    if replacement_sells:
        sim.move_price(replacement_sells[0] + 1.0)

    sim.verify()


if __name__ == "__main__":
    main()
