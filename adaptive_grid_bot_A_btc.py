import os
import time
from decimal import Decimal, ROUND_DOWN

from dotenv import load_dotenv
import okx.Account as Account

from order_manager import OrderManager
from market_data import get_candles, candles_to_dataframe


# ============================================================
# ADAPTIVE GRID BOT v4.8 DEMO
# FIRST REAL DEMO EXECUTION
# ============================================================

load_dotenv()

INST_ID = "BTC-USDT"

# Strategy limits
STRATEGY_CAPITAL_USDT = Decimal("1000.00")
MAX_EXPOSURE_USDT = Decimal("500.00")
ORDER_SIZE_USDT = Decimal("5.00")

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


def run_cycle():
    """Run one safe BTC grid maintenance cycle."""
    flag = os.getenv("OKX_FLAG")
    if flag != "1":
        raise RuntimeError(
            "ABORTED: Bot A only permits OKX DEMO (OKX_FLAG=1)."
        )

    balances = account_balance()
    usdt = balances.get("USDT", Decimal("0"))
    btc = balances.get("BTC", Decimal("0"))

    price, atr = get_market_data()
    atr_percent = atr / price
    regime, grid_percent = determine_regime(atr_percent)

    manager = OrderManager()
    open_orders = manager.get_open_orders()

    current_exposure = sum(
        D(order.get("px", "0")) * D(order.get("sz", "0"))
        for order in open_orders
    )
    buy_count = sum(
        str(order.get("side", "")).lower() == "buy"
        for order in open_orders
    )
    sell_count = sum(
        str(order.get("side", "")).lower() == "sell"
        for order in open_orders
    )

    print("=" * 76)
    print(f"BOT A LOOP | BTC-USDT | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Price ${price:,.2f} | ATR {atr_percent * 100:.4f}% | {regime} | Grid {grid_percent * 100:.4f}%")
    print(f"Open {len(open_orders)} | BUY {buy_count} | SELL {sell_count} | Exposure ${current_exposure:,.2f}")
    print(f"Balance USDT {usdt} | BTC {btc}")

    if current_exposure > MAX_EXPOSURE_USDT:
        raise RuntimeError("ABORTED: Existing BTC exposure exceeds cap.")

    if len(open_orders) > BUY_LEVELS + SELL_LEVELS:
        raise RuntimeError("ABORTED: More than 20 BTC open orders exist.")

    # Bootstrap/reconcile only when the account is empty. Once a grid exists,
    # do not rebuild it at every tick; this prevents duplicate/moving grids.
    if open_orders:
        print("[SAFE] Existing BTC grid detected; no duplicate orders submitted.")
        return

    grid = build_grid(price, grid_percent)
    remaining_exposure = MAX_EXPOSURE_USDT - current_exposure
    capacity = int(remaining_exposure / ORDER_SIZE_USDT)
    orders_to_place = grid[:min(len(grid), capacity)]

    new_sells = [x for x in orders_to_place if x["side"] == "sell"]
    required_sell_btc = sum(
        (D(ORDER_SIZE_USDT) / item["price"] for item in new_sells),
        Decimal("0"),
    )

    if new_sells and btc < required_sell_btc:
        print("[SAFE] SELL orders blocked: insufficient demo BTC.")
        orders_to_place = [x for x in orders_to_place if x["side"] != "sell"]

    placed = 0
    failed = 0
    for item in orders_to_place:
        try:
            response = manager.place_limit_order(
                side=item["side"],
                price=item["price"],
                usdt_size=ORDER_SIZE_USDT,
            )
            ord_id = response.get("data", [{}])[0].get("ordId", "")
            print(f"[PLACED] {item['side'].upper():4} ${item['price']:,.1f} | Order {ord_id}")
            placed += 1
        except Exception as exc:
            failed += 1
            print(f"[FAILED] {item['side'].upper():4} ${item['price']:,.1f} | {exc}")

    final_orders = manager.get_open_orders()
    print(f"[RESULT] submitted={placed} failed={failed} open_orders={len(final_orders)}")


def main():
    interval = int(os.getenv("BOT_A_INTERVAL_SECONDS", "60"))
    if interval < 10:
        interval = 10

    print("=" * 76)
    print("      ADAPTIVE GRID BOT A | BTC-USDT v4.8")
    print("      OKX DEMO | ACCOUNT A | SAFE RECONCILE")
    print("=" * 76)
    print(f"Check interval : {interval} seconds")
    print("Mode           : OKX DEMO ONLY")
    print("Behavior       : SAFE RECONCILE")
    print("Ctrl+C         : STOP")
    print()

    cycle = 0
    while True:
        cycle += 1
        print("=" * 76)
        print(f" SMART LOOP CYCLE {cycle} | BOT A | BTC-USDT | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 76)
        try:
            run_cycle()
        except KeyboardInterrupt:
            print("\nBOT A STOPPED BY USER")
            break
        except Exception as exc:
            print(f"[LOOP ERROR] {exc}")

        print(f"[SLEEP] Next cycle in {interval}s")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nBOT A STOPPED BY USER")
            break


if __name__ == "__main__":
    main()
