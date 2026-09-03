import os
import time
import json
import argparse
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

# Load v4.9 demo credentials before importing the ETH exchange adapter.
load_dotenv(".env.v49", override=True)

from eth_order_manager_v049 import OrderManager
from market_data import get_candles, candles_to_dataframe


# ============================================================
# ADAPTIVE GRID BOT v4.9 - ETH/USDT
# DEMO SMART RECONCILIATION LOOP
# Built from the BTC v4.9 architecture, ETH-specific adapter.
# ============================================================

INST_ID = "ETH-USDT"

STRATEGY_CAPITAL_USDT = Decimal("1000.00")
MAX_EXPOSURE_USDT = Decimal("500.00")
ORDER_SIZE_USDT = Decimal("5.00")
MAX_INVENTORY_USDT = Decimal("1050.00")

BUY_LEVELS = 10
SELL_LEVELS = 10
ATR_PERIOD = 30

LOW_THRESHOLD = Decimal("0.01")
NORMAL_THRESHOLD = Decimal("0.02")
HIGH_THRESHOLD = Decimal("0.03")

GRID_LOW = Decimal("0.0005")
GRID_NORMAL = Decimal("0.0010")
GRID_HIGH = Decimal("0.0020")
GRID_EXTREME = Decimal("0.0030")

GRID_STATE_FILE = "eth_adaptive_grid_v049_demo_state.json"
REBUILD_AFTER_GRID_STEPS = Decimal("1.0")


def D(value):
    return Decimal(str(value))


def get_market_data():
    candles = get_candles(
        inst_id=INST_ID,
        bar="1D",
        limit="100",
    )
    df = candles_to_dataframe(candles)

    if len(df) < ATR_PERIOD + 1:
        raise RuntimeError(f"Not enough ETH candles: {len(df)}")

    previous_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - previous_close).abs()
    tr3 = (df["low"] - previous_close).abs()
    true_range = tr1.to_frame("tr1").join(
        tr2.to_frame("tr2")
    ).join(
        tr3.to_frame("tr3")
    ).max(axis=1)

    atr = true_range.ewm(
        alpha=1 / ATR_PERIOD,
        adjust=False,
    ).mean()

    latest = df.iloc[-1]
    return D(latest["close"]), D(atr.iloc[-1])


def determine_regime(atr_percent):
    if atr_percent < LOW_THRESHOLD:
        return "LOW", GRID_LOW
    if atr_percent < NORMAL_THRESHOLD:
        return "NORMAL", GRID_NORMAL
    if atr_percent < HIGH_THRESHOLD:
        return "HIGH", GRID_HIGH
    return "EXTREME", GRID_EXTREME


def build_grid(anchor_price, grid_percent, manager):
    grid = []

    for level in range(1, BUY_LEVELS + 1):
        raw_price = anchor_price * (D("1") - grid_percent * level)
        grid.append({
            "level": -level,
            "side": "buy",
            "price": manager.normalize_price(raw_price),
        })

    for level in range(1, SELL_LEVELS + 1):
        raw_price = anchor_price * (D("1") + grid_percent * level)
        grid.append({
            "level": level,
            "side": "sell",
            "price": manager.normalize_price(raw_price),
        })

    return grid


def load_grid_state():
    path = Path(GRID_STATE_FILE)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[STATE WARNING] Cannot read {path}: {exc}")
        return None


def save_grid_state(state):
    Path(GRID_STATE_FILE).write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def infer_anchor_from_orders(open_orders, manager):
    prices = []
    for order in open_orders:
        try:
            price = D(order.get("px", "0"))
            if price > 0:
                prices.append(price)
        except Exception:
            pass

    if len(prices) < 2:
        return None

    return manager.normalize_price(
        (min(prices) + max(prices)) / D("2")
    )


def should_rebuild_grid(current_price, anchor_price, current_regime, state, grid_percent):
    if anchor_price is None:
        return True

    previous_regime = state.get("regime") if state else None
    if previous_regime and previous_regime != current_regime:
        return True

    step = anchor_price * grid_percent
    if step <= 0:
        return False

    return abs(current_price - anchor_price) >= step * REBUILD_AFTER_GRID_STEPS


def get_target_grid(open_orders, manager):
    price, atr = get_market_data()
    atr_percent = atr / price
    regime, grid_percent = determine_regime(atr_percent)
    state = load_grid_state()

    anchor = None
    if state:
        try:
            anchor = D(str(state.get("anchor_price")))
            anchor = manager.normalize_price(anchor)
        except Exception:
            anchor = None

    if anchor is None and len(open_orders) >= 10:
        anchor = infer_anchor_from_orders(open_orders, manager)
        if anchor is not None:
            print(f"[STATE RECOVERED] ETH anchor: ${anchor:,.2f}")

    rebuild = should_rebuild_grid(
        current_price=price,
        anchor_price=anchor,
        current_regime=regime,
        state=state or {},
        grid_percent=grid_percent,
    )

    if rebuild:
        anchor = manager.normalize_price(price)
        state = {
            "symbol": INST_ID,
            "anchor_price": str(anchor),
            "regime": regime,
            "grid_percent": str(grid_percent),
        }
        save_grid_state(state)
        print(f"[GRID REBUILD] ETH anchor: ${anchor:,.2f}")
    else:
        print(f"[GRID HOLD] ETH anchor: ${anchor:,.2f}")

    return {
        "price": price,
        "atr": atr,
        "atr_percent": atr_percent,
        "regime": regime,
        "grid_percent": grid_percent,
        "anchor_price": anchor,
        "grid": build_grid(anchor, grid_percent, manager),
        "rebuild": rebuild,
    }


def normalize_target_order(order):
    return {
        "side": str(order.get("side", "")).lower(),
        "price": float(order.get("price")),
        "level": order.get("level"),
    }


def normalize_open_order(order):
    price = order.get("px")
    if price is None:
        raise RuntimeError(f"Open order has no price: {order}")
    return {
        "ordId": order.get("ordId"),
        "side": str(order.get("side", "")).lower(),
        "price": float(price),
        "sz": D(order.get("sz", "0")),
    }


def prices_match(a, b, manager):
    a = D(a)
    b = D(b)
    tolerance = manager.tick_size * D("0.51")
    return abs(a - b) <= tolerance


def reconcile_orders(target_grid, open_orders, manager):
    target = [normalize_target_order(x) for x in target_grid]
    existing = [normalize_open_order(x) for x in open_orders]

    used_existing = set()
    stale = []
    missing = []

    for target_order in target:
        matched_index = None
        for index, existing_order in enumerate(existing):
            if index in used_existing:
                continue
            if existing_order["side"] != target_order["side"]:
                continue
            if not prices_match(existing_order["price"], target_order["price"], manager):
                continue
            matched_index = index
            break

        if matched_index is None:
            missing.append(target_order)
        else:
            used_existing.add(matched_index)

    for index, order in enumerate(existing):
        if index not in used_existing:
            stale.append(order)

    return stale, missing


def calculate_exposure(open_orders):
    return sum(
        (
            D(order.get("px", "0")) * D(order.get("sz", "0"))
            for order in open_orders
        ),
        D("0"),
    )


def apply_inventory_protection(missing, open_orders, eth_balance, price):
    actual_eth = D(eth_balance)
    pending_buy_eth = sum(
        (
            D(order.get("sz", "0"))
            for order in open_orders
            if str(order.get("side", "")).lower() == "buy"
        ),
        D("0"),
    )

    inventory_eth = actual_eth + pending_buy_eth
    inventory_usdt = inventory_eth * D(price)

    buy_missing = [x for x in missing if x["side"] == "buy"]
    sell_missing = [x for x in missing if x["side"] == "sell"]

    allowed_buys = []
    projected = inventory_usdt
    for item in buy_missing:
        if projected + ORDER_SIZE_USDT <= MAX_INVENTORY_USDT:
            allowed_buys.append(item)
            projected += ORDER_SIZE_USDT
        else:
            break

    print()
    print("=" * 76)
    print("ETH v4.9 INVENTORY PROTECTION")
    print("=" * 76)
    print(f"Actual ETH        : {actual_eth}")
    print(f"Pending BUY ETH   : {pending_buy_eth}")
    print(f"Inventory ETH     : {inventory_eth}")
    print(f"Inventory Value   : ${inventory_usdt:,.2f}")
    print(f"Inventory Cap     : ${MAX_INVENTORY_USDT:,.2f}")
    print(f"Projected Value   : ${projected:,.2f}")
    allowed_sells = []
    available_sell_eth = actual_eth
    for item in sell_missing:
        required_eth = ORDER_SIZE_USDT / D(item["price"])
        if available_sell_eth >= required_eth:
            allowed_sells.append(item)
            available_sell_eth -= required_eth
        else:
            break

    print(f"BUY Missing       : {len(buy_missing)}")
    print(f"BUY Allowed       : {len(allowed_buys)}")
    print(f"SELL Missing      : {len(sell_missing)}")
    print(f"SELL Allowed      : {len(allowed_sells)}")

    if sell_missing and not allowed_sells:
        print("[SELL PROTECTION] SELL orders blocked: insufficient actual ETH inventory.")

    return allowed_buys + allowed_sells


def run_cycle(manager, cycle, dry_run=False):
    print()
    print("=" * 76)
    print(f" ETH v4.9 DEMO SMART LOOP CYCLE {cycle} ")
    print(f" {time.strftime('%Y-%m-%d %H:%M:%S')} ")
    print("=" * 76)

    if os.getenv("OKX_FLAG") != "1":
        raise RuntimeError("ABORTED: ETH v4.9 only permits OKX DEMO (OKX_FLAG=1).")

    open_orders = manager.get_open_orders()
    print(f"Open orders       : {len(open_orders)}")

    state = get_target_grid(open_orders, manager)
    print(f"ETH price         : ${state['price']:,.2f}")
    print(f"ATR               : ${state['atr']:,.2f}")
    print(f"ATR / Price       : {state['atr_percent'] * 100:.4f}%")
    print(f"Regime            : {state['regime']}")
    print(f"Grid distance     : {state['grid_percent'] * 100:.4f}%")
    print(f"Grid anchor       : ${state['anchor_price']:,.2f}")
    print(f"Grid rebuild      : {state['rebuild']}")

    stale, missing = reconcile_orders(state["grid"], open_orders, manager)
    print(f"Target orders     : {len(state['grid'])}")
    print(f"Stale orders      : {len(stale)}")
    print(f"Missing orders    : {len(missing)}")

    if not state["rebuild"]:
        if stale:
            print("[GRID HOLD] Existing orders kept; no stale cancellation.")
        stale = []

    if dry_run and stale:
        print(f"[DRY RUN] Would cancel {len(stale)} stale ETH order(s); none will be cancelled.")
        stale = []

    for order in stale:
        ord_id = order.get("ordId")
        if not ord_id:
            print("[SAFE SKIP] Stale ETH order has no ID.")
            missing = []
            continue
        try:
            manager.cancel_order(ord_id)
            print(f"[CANCELLED] {order['side'].upper()} | ${order['price']:,.2f} | {ord_id}")
        except Exception as exc:
            print(f"[CANCEL FAILED] {ord_id} | {exc}")
            missing = []
            break

    current_orders = manager.get_open_orders()
    _, missing = reconcile_orders(state["grid"], current_orders, manager)

    current_exposure = calculate_exposure(current_orders)
    capacity = int((MAX_EXPOSURE_USDT - current_exposure) / ORDER_SIZE_USDT)
    if capacity < 0:
        capacity = 0
    if len(missing) > capacity:
        print(f"[RISK CAP] Missing={len(missing)} capacity={capacity}; limiting new orders.")
        missing = missing[:capacity]

    balances = manager.get_balances()
    eth_balance = balances.get("ETH", D("0"))
    missing = apply_inventory_protection(
        missing,
        current_orders,
        eth_balance,
        state["price"],
    )

    if not missing:
        print("[NO CHANGE] No ETH orders need to be placed.")
        return

    if dry_run:
        print()
        print("=" * 76)
        print("ETH v4.9 DRY RUN - NO ORDERS SUBMITTED")
        print("=" * 76)
        for order in missing:
            print(
                f"[WOULD PLACE] Level {str(order.get('level', '')).rjust(3)} "
                f"| {order['side'].upper():4} | ${order['price']:,.2f}"
            )
        return

    print()
    print("=" * 76)
    print("ETH v4.9 SUBMITTING DEMO ORDERS")
    print("=" * 76)

    for order in missing:
        try:
            response = manager.place_limit_order(
                side=order["side"],
                price=order["price"],
                usdt_size=ORDER_SIZE_USDT,
            )
            data = response.get("data", [])
            ord_id = data[0].get("ordId", "") if data else ""
            print(
                f"[PLACED] Level {str(order.get('level', '')).rjust(3)} "
                f"| {order['side'].upper():4} "
                f"| ${order['price']:,.2f} | {ord_id}"
            )
        except Exception as exc:
            print(
                f"[PLACE FAILED] {order['side'].upper()} "
                f"${order['price']:,.2f} | {exc}"
            )


def smart_loop_main():
    parser = argparse.ArgumentParser(description="ETH Adaptive Grid Bot v4.9 Demo")
    parser.add_argument("--once", action="store_true", help="Run exactly one cycle")
    parser.add_argument("--dry-run", action="store_true", help="Calculate/reconcile only; never submit or cancel orders")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 30 seconds")
    args = parser.parse_args()

    interval = max(10, int(os.getenv("DEMO_LOOP_INTERVAL", "30")))

    print()
    print("=" * 76)
    print("      ADAPTIVE GRID BOT E | ETH-USDT v4.9")
    print("      OKX DEMO | ACCOUNT E | SAFE RECONCILE")
    print("=" * 76)
    print(f"Check interval : {interval} seconds")
    print("Mode           : OKX DEMO ONLY")
    print("Behavior       : SAFE RECONCILE")
    print("Ctrl+C         : STOP")
    print(f"Order size     : ${ORDER_SIZE_USDT:,.2f}")
    print(f"Max exposure   : ${MAX_EXPOSURE_USDT:,.2f}")
    print(f"Grid           : {BUY_LEVELS} BUY / {SELL_LEVELS} SELL")
    print(f"Execution      : {'DRY RUN' if args.dry_run else 'DEMO ORDERS'}")
    print("Safety         : no cancel-all; DEMO flag required")

    manager = OrderManager()
    cycle = 0

    next_run = time.monotonic()

    while True:
        cycle += 1
        cycle_started = time.monotonic()
        try:
            print()
            print("=" * 76)
            print(f" SMART LOOP CYCLE {cycle} | BOT E | ETH-USDT | {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 76)
            run_cycle(manager, cycle, dry_run=args.dry_run)
        except KeyboardInterrupt:
            print("\nETH v4.9 SMART DEMO LOOP STOPPED")
            break
        except Exception as exc:
            print(f"[LOOP ERROR] {exc}")
            print("No automatic cancel-all will be performed.")

        if args.once:
            print("\n[ONCE] Single cycle complete.")
            break

        next_run += interval
        sleep_for = max(0.0, next_run - time.monotonic())
        elapsed = time.monotonic() - cycle_started
        print(f"[NEXT CYCLE] {sleep_for:.1f}s | cycle runtime {elapsed:.1f}s | target interval {interval}s")
        time.sleep(sleep_for)


if __name__ == "__main__":
    smart_loop_main()
