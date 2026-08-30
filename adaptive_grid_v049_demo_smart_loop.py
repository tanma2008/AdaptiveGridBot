import os
import time
import signal
import json
from decimal import Decimal, ROUND_DOWN

from dotenv import load_dotenv

# v4.9 uses Account B only.
# Load .env.v49 BEFORE importing OrderManager because OrderManager
# reads OKX credentials at import time.
load_dotenv('.env.v49', override=True)

import okx.Account as Account
from order_manager import OrderManager
from market_data import get_candles, candles_to_dataframe
from pathlib import Path


# ============================================================
# ADAPTIVE GRID BOT v4.9 DEMO
# FIRST REAL DEMO EXECUTION
# ============================================================

INST_ID = "BTC-USDT"

# Strategy limits
STRATEGY_CAPITAL_USDT = Decimal("1000.00")
MAX_EXPOSURE_USDT = Decimal("500.00")
ORDER_SIZE_USDT = Decimal("5.00")

# v4.9: cap actual + pending BTC inventory created by BUY orders.
# SELL orders are not restricted by this cap.
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


def D(value):
    return Decimal(str(value))


def round_price(price):
    return D(price).quantize(
        Decimal("0.1"),
        rounding=ROUND_DOWN,
    )


def get_market_data():
    candles = get_candles(
        inst_id=INST_ID,
        bar="1D",
        limit="100",
    )

    df = candles_to_dataframe(candles)

    if len(df) < ATR_PERIOD + 1:
        raise RuntimeError(
            f"Not enough candles: {len(df)}"
        )

    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - previous_close).abs()
    tr3 = (df["low"] - previous_close).abs()

    true_range = (
        tr1.to_frame("tr1")
        .join(tr2.to_frame("tr2"))
        .join(tr3.to_frame("tr3"))
        .max(axis=1)
    )

    atr = true_range.ewm(
        alpha=1 / ATR_PERIOD,
        adjust=False,
    ).mean()

    latest = df.iloc[-1]

    return (
        D(latest["close"]),
        D(atr.iloc[-1]),
    )


def determine_regime(atr_percent):
    if atr_percent < LOW_THRESHOLD:
        return "LOW", GRID_LOW

    if atr_percent < NORMAL_THRESHOLD:
        return "NORMAL", GRID_NORMAL

    if atr_percent < HIGH_THRESHOLD:
        return "HIGH", GRID_HIGH

    return "EXTREME", GRID_EXTREME


def build_grid(price, grid_percent):
    grid = []

    for level in range(1, BUY_LEVELS + 1):
        grid_price = price * (
            D("1") - grid_percent * level
        )

        grid.append({
            "level": -level,
            "side": "buy",
            "price": round_price(grid_price),
        })

    for level in range(1, SELL_LEVELS + 1):
        grid_price = price * (
            D("1") + grid_percent * level
        )

        grid.append({
            "level": level,
            "side": "sell",
            "price": round_price(grid_price),
        })

    return grid


def order_matches_grid(order, grid):
    return (
        str(order.get("side", "")).lower()
        == grid["side"]
        and D(order.get("px", "0"))
        == grid["price"]
    )


def account_balance():
    flag = os.getenv("OKX_FLAG")

    if flag != "1":
        raise RuntimeError(
            "SAFETY STOP: OKX_FLAG must be '1' for DEMO. "
            f"Current value={flag!r}"
        )

    api = Account.AccountAPI(
        api_key=os.getenv("OKX_API_KEY"),
        api_secret_key=os.getenv("OKX_SECRET_KEY"),
        passphrase=os.getenv("OKX_PASSPHRASE"),
        flag="1",
        debug=False,
    )

    response = api.get_account_balance()

    if response.get("code") != "0":
        raise RuntimeError(
            f"OKX DEMO Account Error: {response}"
        )

    details = response.get("data", [{}])[0].get(
        "details",
        [],
    )

    balances = {}

    for item in details:
        ccy = item.get("ccy")
        avail = item.get("availBal", "0")

        if ccy:
            balances[ccy] = D(avail)

    return balances


def run_once():
    print()
    print("=" * 76)
    print("        ADAPTIVE GRID BOT v4.9 SMART LOOP")
    print("          OKX DEMO SMART RECONCILIATION LOOP")
    print("=" * 76)

    flag = os.getenv("OKX_FLAG")
    print(f"\nOKX_FLAG          : {flag!r}")
    print(f"Symbol            : {INST_ID}")
    print(f"Strategy Capital  : ${STRATEGY_CAPITAL_USDT:,.2f}")
    print(f"Max Exposure      : ${MAX_EXPOSURE_USDT:,.2f}")
    print(f"Order Size        : ${ORDER_SIZE_USDT:,.2f}")
    print(f"Grid              : {BUY_LEVELS} BUY / {SELL_LEVELS} SELL")
    if flag != "1":
        raise RuntimeError("ABORTED: This runner only permits OKX DEMO (OKX_FLAG=1). No LIVE orders allowed.")

    balances = account_balance()
    usdt = balances.get("USDT", Decimal("0"))
    btc = balances.get("BTC", Decimal("0"))
    print("\n" + "=" * 76 + "\nDEMO ACCOUNT\n" + "=" * 76)
    print(f"Available USDT    : {usdt}")
    print(f"Available BTC     : {btc}")

    price, atr = get_market_data()
    atr_percent = atr / price
    regime, grid_percent = determine_regime(atr_percent)
    print("\n" + "=" * 76 + "\nMARKET STATE\n" + "=" * 76)
    print(f"BTC Price         : ${price:,.2f}")
    print(f"ATR               : ${atr:,.2f}")
    print(f"ATR / Price       : {atr_percent * 100:.4f}%")
    print(f"Regime            : {regime}")
    print(f"Grid Distance     : {grid_percent * 100:.4f}%")

    manager = OrderManager()
    open_orders = manager.get_open_orders()
    current_exposure = sum(D(o.get("px", "0")) * D(o.get("sz", "0")) for o in open_orders)
    buy_count = sum(str(o.get("side", "")).lower() == "buy" for o in open_orders)
    sell_count = sum(str(o.get("side", "")).lower() == "sell" for o in open_orders)
    print("\n" + "=" * 76 + "\nCURRENT DEMO RISK\n" + "=" * 76)
    print(f"Open Orders       : {len(open_orders)}")
    print(f"BUY Orders        : {buy_count}")
    print(f"SELL Orders       : {sell_count}")
    print(f"Exposure          : ${current_exposure:,.2f}")
    print(f"Remaining         : ${MAX_EXPOSURE_USDT - current_exposure:,.2f}")
    if current_exposure > MAX_EXPOSURE_USDT:
        raise RuntimeError("ABORTED: Existing exposure already exceeds cap.")

    grid_state = get_target_grid(open_orders)
    target_grid = grid_state["grid"]
    stale, missing = reconcile_orders(manager, target_grid, open_orders)
    print("\n" + "=" * 76 + "\nRECONCILIATION\n" + "=" * 76)
    print(f"Target orders     : {len(target_grid)}")
    print(f"Stale orders      : {len(stale)}")
    print(f"Missing orders    : {len(missing)}")

    # Reconcile excess/stale orders individually. Never cancel-all.
    for order in stale:
        ord_id = order.get("ordId")
        if not ord_id:
            print("[SAFE SKIP] Stale order has no ID.")
            continue
        try:
            manager.cancel_order(ord_id)
            print(f"[CANCELLED] {order.get('side', '').upper()} | ${D(order.get('px', order.get('price', '0'))):,.1f} | {ord_id}")
        except Exception as exc:
            print(f"[CANCEL FAILED] {ord_id} | {exc}")
            return

    current_orders = manager.get_open_orders()
    _, missing = reconcile_orders(manager, target_grid, current_orders)
    current_exposure = sum(D(o.get("px", "0")) * D(o.get("sz", "0")) for o in current_orders)
    capacity = int(max(Decimal("0"), MAX_EXPOSURE_USDT - current_exposure) / ORDER_SIZE_USDT)
    missing = missing[:capacity]
    new_buys = [x for x in missing if x["side"] == "buy"]
    new_sells = [x for x in missing if x["side"] == "sell"]
    required_sell_btc = sum((D(ORDER_SIZE_USDT) / D(str(x["price"])) for x in new_sells), Decimal("0"))

    print("\n" + "=" * 76 + "\nEXECUTION PREFLIGHT\n" + "=" * 76)
    print(f"New BUY orders     : {len(new_buys)}")
    print(f"New SELL orders    : {len(new_sells)}")
    print(f"Required SELL BTC  : {required_sell_btc}")
    print(f"Available BTC      : {btc}")
    if new_sells and btc < required_sell_btc:
        print("SELL ORDERS BLOCKED: insufficient demo BTC.")
        new_sells = []
    orders_to_place = new_buys + new_sells
    if not orders_to_place:
        print("[NO CHANGE] Demo grid is reconciled; nothing to place.")
        return

    print("\n" + "=" * 76 + "\nSUBMITTING DEMO ORDERS\n" + "=" * 76)
    placed = 0
    failed = 0
    for item in orders_to_place:
        try:
            response = manager.place_limit_order(side=item["side"], price=item["price"], usdt_size=ORDER_SIZE_USDT)
            data = response.get("data", [])
            ord_id = data[0].get("ordId", "") if data else ""
            print(f"[PLACED] Level {item['level']:>3} | {item['side'].upper():4} | ${item['price']:,.1f} | Order {ord_id}")
            placed += 1
        except Exception as exc:
            failed += 1
            print(f"[FAILED] Level {item['level']:>3} | {item['side'].upper():4} | ${item['price']:,.1f} | {exc}")
    final_orders = manager.get_open_orders()
    print("\n" + "=" * 76 + "\nDEMO EXECUTION RESULT\n" + "=" * 76)
    print(f"Orders submitted   : {placed}")
    print(f"Orders failed      : {failed}")
    print(f"Open orders now     : {len(final_orders)}")



def _order_key(side, price, tolerance=0.00015):

    return (
        str(side).lower(),
        round(
            float(price),
            1,
        ),
    )



GRID_STATE_FILE = "adaptive_grid_v049_demo_state.json"

# Do NOT rebuild the grid for every small price movement.
# Rebuild only when price moves at least this many grid spacings
# from the current anchor, or the volatility regime changes.
REBUILD_AFTER_GRID_STEPS = 1.0


def load_grid_state():

    path = Path(GRID_STATE_FILE)

    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        print(
            f"[STATE WARNING] Cannot read {path}: {exc}"
        )
        return None


def save_grid_state(state):

    Path(
        GRID_STATE_FILE
    ).write_text(
        json.dumps(
            state,
            indent=2,
        ),
        encoding="utf-8",
    )


def infer_anchor_from_orders(open_orders):

    """
    Recover the grid anchor from an existing 10-buy / 10-sell
    grid without touching exchange orders.

    The original grid is symmetric around its anchor, so:
        anchor = (min price + max price) / 2

    This is especially useful after restarting the bot.
    """

    prices = []

    for order in open_orders:

        try:
            price = D(
                order.get(
                    "px",
                    "0",
                )
            )

            if price > 0:
                prices.append(
                    price
                )

        except Exception:
            pass

    if len(prices) < 2:
        return None

    return (
        min(prices)
        + max(prices)
    ) / D("2")


def should_rebuild_grid(
    current_price,
    anchor_price,
    current_regime,
    state,
    grid_percent,
):

    if anchor_price is None:
        return True

    previous_regime = (
        state.get("regime")
        if state
        else None
    )

    # A regime change is a genuine strategy change.
    if (
        previous_regime
        and previous_regime != current_regime
    ):
        return True

    distance = abs(
        current_price
        - anchor_price
    )

    step = (
        anchor_price
        * grid_percent
    )

    if step <= 0:
        return False

    return (
        distance
        >= step
        * D(str(REBUILD_AFTER_GRID_STEPS))
    )


def build_anchored_grid(
    anchor_price,
    grid_percent,
):

    return build_grid(
        anchor_price,
        grid_percent,
    )


def get_target_grid(
    open_orders,
):

    """
    State-aware target grid.

    Small price movements do NOT move the grid anchor.
    This prevents cancel/re-place churn every 30 seconds.

    Existing orders are preserved unless:
      1) price moves >= 1 grid spacing from anchor, OR
      2) volatility regime changes.
    """

    price, atr = get_market_data()

    atr_percent = atr / price

    regime, grid_percent = determine_regime(
        atr_percent
    )

    state = load_grid_state()

    anchor = None

    if state:
        try:
            anchor = D(
                str(
                    state.get(
                        "anchor_price"
                    )
                )
            )
        except Exception:
            anchor = None

    # If no saved state exists but orders already exist,
    # infer the previous grid anchor instead of rebuilding
    # around the latest tick.
    if anchor is None and len(open_orders) >= 10:

        anchor = infer_anchor_from_orders(
            open_orders
        )

        if anchor is not None:

            print(
                f"[STATE RECOVERED] "
                f"Anchor from existing grid: "
                f"${anchor:,.1f}"
            )

    rebuild = should_rebuild_grid(
        current_price=D(str(price)),
        anchor_price=anchor,
        current_regime=regime,
        state=state or {},
        grid_percent=D(str(grid_percent)),
    )

    if rebuild:

        anchor = D(
            str(price)
        )

        state = {
            "anchor_price": str(
                round_price(anchor)
            ),
            "regime": regime,
            "grid_percent": str(
                grid_percent
            ),
        }

        save_grid_state(
            state
        )

        print(
            f"[GRID REBUILD] "
            f"New anchor: ${anchor:,.1f}"
        )

    else:

        print(
            f"[GRID HOLD] "
            f"Anchor: ${anchor:,.1f}"
        )

    grid = build_anchored_grid(
        anchor,
        D(str(grid_percent)),
    )

    return {
        "price": D(str(price)),
        "atr": D(str(atr)),
        "atr_percent": D(
            str(atr_percent)
        ),
        "regime": regime,
        "grid_percent": D(
            str(grid_percent)
        ),
        "anchor_price": anchor,
        "grid": grid,
        "rebuild": rebuild,
    }



def normalize_target_order(order):

    if isinstance(order, dict):
        side = order.get(
            "side",
            ""
        )

        price = order.get(
            "price",
            order.get("px")
        )

        level = order.get(
            "level"
        )

        return {
            "side": str(side).lower(),
            "price": float(price),
            "level": level,
        }

    raise RuntimeError(
        f"Unsupported target order format: {order!r}"
    )


def normalize_open_order(order):

    side = str(
        order.get(
            "side",
            ""
        )
    ).lower()

    price = order.get(
        "px"
    )

    if price is None:
        raise RuntimeError(
            f"Open order has no price: {order}"
        )

    return {
        "ordId": order.get(
            "ordId"
        ),
        "side": side,
        "price": float(price),
    }


def prices_match(a, b):

    a = float(a)
    b = float(b)

    if a <= 0 or b <= 0:
        return False

    # BTC-USDT price tolerance:
    # only treat genuinely equivalent prices as the same order.
    return (
        abs(a - b)
        / max(a, b)
        <= 0.00002
    )


def reconcile_orders(
    manager,
    target_grid,
    open_orders,
):

    target = [
        normalize_target_order(x)
        for x in target_grid
    ]

    existing = [
        normalize_open_order(x)
        for x in open_orders
    ]

    used_existing = set()
    stale = []
    missing = []

    # --------------------------------------------------------
    # Match existing orders to target orders.
    # --------------------------------------------------------

    for target_order in target:

        matched_index = None

        for index, existing_order in enumerate(
            existing
        ):

            if index in used_existing:
                continue

            if (
                existing_order["side"]
                != target_order["side"]
            ):
                continue

            if not prices_match(
                existing_order["price"],
                target_order["price"],
            ):
                continue

            matched_index = index
            break

        if matched_index is None:
            missing.append(
                target_order
            )
        else:
            used_existing.add(
                matched_index
            )

    # Anything not matched is stale.
    for index, order in enumerate(
        existing
    ):

        if index not in used_existing:
            stale.append(
                order
            )

    return stale, missing



def calculate_inventory_state(open_orders, btc_balance, price):
    """Return actual BTC + pending BUY BTC inventory exposure."""
    actual_btc = D(btc_balance)
    pending_buy_btc = sum(
        (
            D(order.get("sz", "0"))
            for order in open_orders
            if str(order.get("side", "")).lower() == "buy"
        ),
        Decimal("0"),
    )
    inventory_btc = actual_btc + pending_buy_btc
    inventory_usdt = inventory_btc * D(price)
    return actual_btc, pending_buy_btc, inventory_btc, inventory_usdt


def apply_inventory_protection(missing, open_orders, btc_balance, price):
    """Block only new BUYs that would push inventory above the v4.9 cap."""
    actual_btc, pending_buy_btc, inventory_btc, inventory_usdt = (
        calculate_inventory_state(open_orders, btc_balance, price)
    )

    buy_missing = [
        x for x in missing
        if str(x.get("side", "")).lower() == "buy"
    ]
    sell_missing = [
        x for x in missing
        if str(x.get("side", "")).lower() == "sell"
    ]

    allowed_buys = []
    projected = inventory_usdt

    for item in buy_missing:
        order_usdt = ORDER_SIZE_USDT
        if projected + order_usdt <= MAX_INVENTORY_USDT:
            allowed_buys.append(item)
            projected += order_usdt
        else:
            break

    blocked = len(buy_missing) - len(allowed_buys)

    print()
    print("=" * 76)
    print("V4.9 INVENTORY PROTECTION")
    print("=" * 76)
    print(f"Actual BTC        : {actual_btc}")
    print(f"Pending BUY BTC   : {pending_buy_btc}")
    print(f"Inventory BTC     : {inventory_btc}")
    print(f"Inventory Value   : ${inventory_usdt:,.2f}")
    print(f"Inventory Cap     : ${MAX_INVENTORY_USDT:,.2f}")
    print(f"Projected Value   : ${projected:,.2f}")
    print(f"BUY Missing       : {len(buy_missing)}")
    print(f"BUY Allowed       : {len(allowed_buys)}")
    print(f"SELL Missing      : {len(sell_missing)}")

    if blocked:
        print(f"[INVENTORY PROTECTION] Blocked {blocked} new BUY order(s).")
    else:
        print("[INVENTORY OK] BUY inventory within cap.")

    return allowed_buys + sell_missing


def smart_loop_main():

    interval = int(
        os.getenv(
            "DEMO_LOOP_INTERVAL",
            "30",
        )
    )

    if interval < 10:
        interval = 10

    print()
    print("=" * 76)
    print("       ADAPTIVE GRID BOT v4.9 SMART DEMO LOOP")
    print("=" * 76)
    print()
    print(f"Check interval : {interval} seconds")
    print("Mode           : OKX DEMO ONLY")
    print("Behavior       : RECONCILE ONLY")
    print("Ctrl+C         : STOP")
    print()
    print(
        "NO periodic cancel-all."
    )
    print(
        "Orders are cancelled only when stale."
    )
    print(
        "Orders are placed only when missing."
    )
    print()

    cycle = 0

    while True:

        cycle += 1

        print()
        print("=" * 76)
        print(
            f" SMART LOOP CYCLE {cycle} "
            f"| {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print("=" * 76)

        try:

            manager = OrderManager()

            open_orders = (
                manager.get_open_orders()
            )

            print(
                f"Open orders       : "
                f"{len(open_orders)}"
            )

            # ------------------------------------------------
            # Build target grid without submitting anything.
            # ------------------------------------------------

            try:
                state = get_target_grid(open_orders)
                target_grid = state["grid"]

            except Exception as exc:

                print(
                    "[SAFE STOP] "
                    "Could not calculate target grid."
                )
                print(
                    f"Reason: {exc}"
                )
                print(
                    "No orders will be modified."
                )

                time.sleep(interval)
                continue

            print(
                f"BTC price         : "
                f"${state['price']:,.2f}"
            )
            print(
                f"ATR               : "
                f"${state['atr']:,.2f}"
            )
            print(
                f"Regime            : "
                f"{state['regime']}"
            )
            print(
                f"Grid distance     : "
                f"{state['grid_percent'] * 100:.4f}%"
            )
            print(
                f"Grid anchor       : "
                f"${state['anchor_price']:,.1f}"
            )
            print(
                f"Grid rebuild      : "
                f"{state['rebuild']}"
            )

            stale, missing = (
                reconcile_orders(
                    manager,
                    target_grid,
                    open_orders,
                )
            )

            print(
                f"Target orders     : "
                f"{len(target_grid)}"
            )
            print(
                f"Stale orders      : "
                f"{len(stale)}"
            )
            print(
                f"Missing orders    : "
                f"{len(missing)}"
            )

            # ------------------------------------------------
            # SAFETY RULE:
            #
            # If the anchor/grid has NOT been rebuilt, NEVER
            # cancel existing orders just because the market
            # price moved.
            #
            # Only fill the missing level(s).
            # ------------------------------------------------

            if not state["rebuild"]:

                if stale:

                    print(
                        "[GRID HOLD] Existing orders are "
                        "kept. No stale cancellation."
                    )

                stale = []

            # ------------------------------------------------
            # No changes at all.
            # ------------------------------------------------

            if not stale and not missing:

                print(
                    "[NO CHANGE] "
                    "Grid already matches target."
                )

                time.sleep(interval)
                continue

            # ------------------------------------------------
            # Cancel stale orders ONLY after a real grid
            # rebuild.
            # ------------------------------------------------

            for order in stale:

                ord_id = order.get(
                    "ordId"
                )

                if not ord_id:
                    print(
                        "[SAFE SKIP] "
                        "Stale order has no ID."
                    )
                    continue

                try:

                    manager.cancel_order(
                        ord_id
                    )

                    print(
                        f"[CANCELLED] "
                        f"{order['side'].upper()} "
                        f"| ${order['price']:,.1f} "
                        f"| {ord_id}"
                    )

                except Exception as exc:

                    print(
                        f"[CANCEL FAILED] "
                        f"{ord_id} | {exc}"
                    )

                    # Do NOT place replacements if a stale
                    # order could not be removed.
                    missing = []

                    break

            # ------------------------------------------------
            # Re-read after cancellation.
            # ------------------------------------------------

            if missing:

                try:
                    current_orders = (
                        manager.get_open_orders()
                    )
                except Exception as exc:

                    print(
                        "[SAFE STOP] "
                        f"Could not re-read orders: {exc}"
                    )

                    time.sleep(interval)
                    continue

                # Reconcile again so we never create a
                # duplicate order after a race.
                _, missing = (
                    reconcile_orders(
                        manager,
                        target_grid,
                        current_orders,
                    )
                )

            # ------------------------------------------------
            # Place ONLY missing orders.
            # ------------------------------------------------

            current_orders_after_cancel = (
                manager.get_open_orders()
            )

            current_exposure_after_cancel = sum(
                (
                    D(x.get("px", "0"))
                    * D(x.get("sz", "0"))
                    for x in current_orders_after_cancel
                ),
                Decimal("0"),
            )

            available_capacity = (
                MAX_EXPOSURE_USDT
                - current_exposure_after_cancel
            )

            max_new_orders = int(
                available_capacity
                / ORDER_SIZE_USDT
            )

            if max_new_orders < 0:
                max_new_orders = 0

            if len(missing) > max_new_orders:
                print(
                    f"[RISK CAP] Missing={len(missing)} "
                    f"but capacity={max_new_orders}. "
                    "Only capacity will be placed."
                )
                missing = missing[:max_new_orders]

            # ------------------------------------------------
            # v4.9 INVENTORY PROTECTION
            # ------------------------------------------------
            try:
                balances = account_balance()
                current_btc = balances.get("BTC", Decimal("0"))
            except Exception as exc:
                print(
                    "[SAFE STOP] Could not read BTC balance "
                    f"for inventory protection: {exc}"
                )
                time.sleep(interval)
                continue

            missing = apply_inventory_protection(
                missing=missing,
                open_orders=current_orders_after_cancel,
                btc_balance=current_btc,
                price=state["price"],
            )

            for order in missing:

                try:

                    # Use the same existing v4.8 order manager
                    # interface: side, price, USDT size.
                    response = (
                        manager.place_limit_order(
                            side=order["side"],
                            price=order["price"],
                            usdt_size=ORDER_SIZE_USDT,
                        )
                    )

                    data = response.get(
                        "data",
                        []
                    )

                    ord_id = (
                        data[0].get("ordId")
                        if data
                        else ""
                    )

                    print(
                        f"[PLACED] "
                        f"Level {str(order.get('level','')).rjust(3)} "
                        f"| {order['side'].upper():4} "
                        f"| ${order['price']:,.1f} "
                        f"| {ord_id}"
                    )

                except Exception as exc:

                    print(
                        f"[PLACE FAILED] "
                        f"{order['side'].upper()} "
                        f"${order['price']:,.1f} "
                        f"| {exc}"
                    )

            print()
            print(
                "Cycle complete."
            )
            print(
                f"Next check in {interval} seconds..."
            )

            time.sleep(interval)

        except KeyboardInterrupt:

            print()
            print("=" * 76)
            print(
                "       SMART DEMO LOOP STOPPED"
            )
            print("=" * 76)
            print(
                "Existing OKX Demo orders were left "
                "untouched."
            )
            print()
            break

        except Exception as exc:

            print(
                f"[LOOP ERROR] {exc}"
            )
            print(
                "No automatic cancel-all will be performed."
            )

            time.sleep(interval)



if __name__ == "__main__":
    smart_loop_main()

