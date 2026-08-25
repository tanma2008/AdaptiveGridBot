import os
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


def main():
    print()
    print("=" * 76)
    print("        ADAPTIVE GRID BOT v4.8")
    print("          OKX DEMO FIRST RUN")
    print("=" * 76)

    # --------------------------------------------------------
    # HARD DEMO SAFETY
    # --------------------------------------------------------
    flag = os.getenv("OKX_FLAG")

    print()
    print(f"OKX_FLAG          : {flag!r}")
    print(f"Symbol            : {INST_ID}")
    print(f"Strategy Capital  : ${STRATEGY_CAPITAL_USDT:,.2f}")
    print(f"Max Exposure      : ${MAX_EXPOSURE_USDT:,.2f}")
    print(f"Order Size        : ${ORDER_SIZE_USDT:,.2f}")
    print(f"Grid              : {BUY_LEVELS} BUY / {SELL_LEVELS} SELL")

    if flag != "1":
        raise RuntimeError(
            "ABORTED: This runner only permits OKX DEMO "
            "(OKX_FLAG=1). No LIVE orders allowed."
        )

    # --------------------------------------------------------
    # ACCOUNT PRE-FLIGHT
    # --------------------------------------------------------
    balances = account_balance()

    usdt = balances.get("USDT", Decimal("0"))
    btc = balances.get("BTC", Decimal("0"))

    print()
    print("=" * 76)
    print("DEMO ACCOUNT")
    print("=" * 76)
    print(f"Available USDT    : {usdt}")
    print(f"Available BTC     : {btc}")

    # --------------------------------------------------------
    # MARKET
    # --------------------------------------------------------
    price, atr = get_market_data()
    atr_percent = atr / price
    regime, grid_percent = determine_regime(atr_percent)

    print()
    print("=" * 76)
    print("MARKET STATE")
    print("=" * 76)
    print(f"BTC Price         : ${price:,.2f}")
    print(f"ATR               : ${atr:,.2f}")
    print(f"ATR / Price       : {atr_percent * 100:.4f}%")
    print(f"Regime            : {regime}")
    print(f"Grid Distance     : {grid_percent * 100:.4f}%")

    # --------------------------------------------------------
    # OPEN ORDERS
    # --------------------------------------------------------
    manager = OrderManager()
    open_orders = manager.get_open_orders()

    current_exposure = Decimal("0")
    buy_count = 0
    sell_count = 0

    for order in open_orders:
        side = str(order.get("side", "")).lower()
        order_value = (
            D(order.get("px", "0"))
            * D(order.get("sz", "0"))
        )

        current_exposure += order_value

        if side == "buy":
            buy_count += 1
        elif side == "sell":
            sell_count += 1

    print()
    print("=" * 76)
    print("CURRENT DEMO RISK")
    print("=" * 76)
    print(f"Open Orders       : {len(open_orders)}")
    print(f"BUY Orders        : {buy_count}")
    print(f"SELL Orders       : {sell_count}")
    print(f"Exposure          : ${current_exposure:,.2f}")
    print(
        f"Remaining         : "
        f"${MAX_EXPOSURE_USDT - current_exposure:,.2f}"
    )

    if current_exposure > MAX_EXPOSURE_USDT:
        raise RuntimeError(
            "ABORTED: Existing exposure already exceeds cap."
        )

    if len(open_orders) > 20:
        raise RuntimeError(
            "ABORTED: More than 20 open orders already exist."
        )

    # --------------------------------------------------------
    # BUILD TARGET GRID
    # --------------------------------------------------------
    grid = build_grid(
        price,
        grid_percent,
    )

    missing = []

    for item in grid:
        matches = [
            order
            for order in open_orders
            if order_matches_grid(order, item)
        ]

        if not matches:
            missing.append(item)

    remaining_exposure = (
        MAX_EXPOSURE_USDT
        - current_exposure
    )

    capacity = int(
        remaining_exposure
        / ORDER_SIZE_USDT
    )

    if len(missing) > capacity:
        missing = missing[:capacity]

    print()
    print("=" * 76)
    print("TARGET DEMO GRID")
    print("=" * 76)

    for item in grid:
        exists = any(
            order_matches_grid(order, item)
            for order in open_orders
        )

        print(
            f"[{'EXISTS' if exists else 'NEW':6}] "
            f"Level {item['level']:>3} | "
            f"{item['side'].upper():4} | "
            f"${item['price']:,.1f}"
        )

    # --------------------------------------------------------
    # SELL PREFLIGHT
    #
    # Spot SELL orders require BTC inventory. Do not submit
    # SELL orders if demo BTC balance is insufficient.
    # --------------------------------------------------------
    new_buys = [
        x for x in missing
        if x["side"] == "buy"
    ]

    new_sells = [
        x for x in missing
        if x["side"] == "sell"
    ]

    required_sell_btc = sum(
        (
            D(ORDER_SIZE_USDT)
            / item["price"]
            for item in new_sells
        ),
        Decimal("0"),
    )

    print()
    print("=" * 76)
    print("EXECUTION PREFLIGHT")
    print("=" * 76)
    print(f"New BUY orders     : {len(new_buys)}")
    print(f"New SELL orders    : {len(new_sells)}")
    print(f"Required SELL BTC  : {required_sell_btc}")
    print(f"Available BTC      : {btc}")

    if new_sells and btc < required_sell_btc:
        print()
        print(
            "SELL ORDERS BLOCKED: insufficient demo BTC."
        )
        print(
            "BUY orders may still be submitted."
        )
        new_sells = []

    orders_to_place = new_buys + new_sells

    if not orders_to_place:
        print()
        print("Nothing to place. Demo grid is already complete.")
        return

    print()
    print("=" * 76)
    print("SUBMITTING DEMO ORDERS")
    print("=" * 76)

    placed = 0
    failed = 0

    for item in orders_to_place:
        try:
            response = manager.place_limit_order(
                side=item["side"],
                price=item["price"],
                usdt_size=ORDER_SIZE_USDT,
            )

            ord_id = (
                response.get("data", [{}])[0]
                .get("ordId", "")
            )

            print(
                f"[PLACED] Level {item['level']:>3} | "
                f"{item['side'].upper():4} | "
                f"${item['price']:,.1f} | "
                f"Order {ord_id}"
            )

            placed += 1

        except Exception as exc:
            failed += 1
            print(
                f"[FAILED] Level {item['level']:>3} | "
                f"{item['side'].upper():4} | "
                f"${item['price']:,.1f} | "
                f"{exc}"
            )

    # --------------------------------------------------------
    # VERIFY
    # --------------------------------------------------------
    final_orders = manager.get_open_orders()

    print()
    print("=" * 76)
    print("DEMO EXECUTION RESULT")
    print("=" * 76)
    print(f"Orders submitted   : {placed}")
    print(f"Orders failed      : {failed}")
    print(f"Open orders now     : {len(final_orders)}")

    print()
    print("=" * 76)
    print("        ADAPTIVE GRID BOT v4.8 DEMO OK")
    print("=" * 76)


if __name__ == "__main__":
    main()
