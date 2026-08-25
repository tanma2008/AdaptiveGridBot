import os
from decimal import Decimal, ROUND_DOWN

from dotenv import load_dotenv

from order_manager import OrderManager
from market_data import get_candles, candles_to_dataframe


# ============================================================
# ADAPTIVE GRID BOT v4.3
# RISK CONTROL / DRY RUN
# ============================================================

load_dotenv()

INST_ID = "BTC-USDT"


# ============================================================
# STRATEGY CAPITAL
# ============================================================

STRATEGY_CAPITAL_USDT = Decimal("1000.00")

MAX_EXPOSURE_USDT = Decimal("500.00")

ORDER_SIZE_USDT = Decimal("5.00")


# ============================================================
# ORDER LIMITS
# ============================================================

MAX_TOTAL_ORDERS = int(
    MAX_EXPOSURE_USDT / ORDER_SIZE_USDT
)

MAX_BUY_ORDERS = MAX_TOTAL_ORDERS // 2
MAX_SELL_ORDERS = MAX_TOTAL_ORDERS // 2


# ============================================================
# ADAPTIVE GRID
# ============================================================

ATR_PERIOD = 30

BUY_LEVELS = 10
SELL_LEVELS = 10


# ============================================================
# VOLATILITY REGIME
# ============================================================

LOW_THRESHOLD = Decimal("0.01")
NORMAL_THRESHOLD = Decimal("0.02")
HIGH_THRESHOLD = Decimal("0.03")

GRID_LOW = Decimal("0.0005")
GRID_NORMAL = Decimal("0.0010")
GRID_HIGH = Decimal("0.0020")
GRID_EXTREME = Decimal("0.0030")


# ============================================================
# MODE
# ============================================================

DRY_RUN = True


# ============================================================
# HELPERS
# ============================================================

def D(value):
    return Decimal(str(value))


def round_price(price):

    return D(price).quantize(
        Decimal("0.1"),
        rounding=ROUND_DOWN,
    )


# ============================================================
# MARKET DATA
# ============================================================

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

    tr2 = (
        df["high"] - previous_close
    ).abs()

    tr3 = (
        df["low"] - previous_close
    ).abs()

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

    price = D(latest["close"])
    atr_value = D(atr.iloc[-1])

    return price, atr_value


# ============================================================
# VOLATILITY REGIME
# ============================================================

def determine_regime(atr_percent):

    if atr_percent < LOW_THRESHOLD:
        return "LOW", GRID_LOW

    if atr_percent < NORMAL_THRESHOLD:
        return "NORMAL", GRID_NORMAL

    if atr_percent < HIGH_THRESHOLD:
        return "HIGH", GRID_HIGH

    return "EXTREME", GRID_EXTREME


# ============================================================
# GRID BUILDER
# ============================================================

def build_grid(
    price,
    grid_percent,
):

    grid = []

    for level in range(1, BUY_LEVELS + 1):

        grid_price = price * (
            D("1")
            - grid_percent * level
        )

        grid.append({
            "level": -level,
            "side": "buy",
            "price": round_price(grid_price),
        })

    for level in range(1, SELL_LEVELS + 1):

        grid_price = price * (
            D("1")
            + grid_percent * level
        )

        grid.append({
            "level": level,
            "side": "sell",
            "price": round_price(grid_price),
        })

    return grid


# ============================================================
# EXISTING ORDER MATCH
# ============================================================

def order_matches_grid(order, grid):

    side = str(
        order.get("side", "")
    ).lower()

    price = D(
        order.get("px", "0")
    )

    return (
        side == grid["side"]
        and price == grid["price"]
    )


def find_existing_orders(
    grid,
    open_orders,
):

    return [
        order
        for order in open_orders
        if order_matches_grid(
            order,
            grid,
        )
    ]


# ============================================================
# RISK CALCULATION
# ============================================================

def calculate_risk(
    open_orders,
):

    buy_orders = 0
    sell_orders = 0

    exposure = Decimal("0")

    for order in open_orders:

        side = str(
            order.get("side", "")
        ).lower()

        price = D(
            order.get("px", "0")
        )

        size = D(
            order.get("sz", "0")
        )

        order_value = (
            price * size
        )

        exposure += order_value

        if side == "buy":
            buy_orders += 1

        elif side == "sell":
            sell_orders += 1

    return (
        buy_orders,
        sell_orders,
        exposure,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print("             ADAPTIVE GRID BOT v4.3")
    print("              RISK CONTROL / DRY RUN")
    print("=" * 72)

    print()
    print(
        f"Exchange          : OKX DEMO"
    )

    print(
        f"Symbol            : {INST_ID}"
    )

    print(
        f"Strategy Capital  : "
        f"{STRATEGY_CAPITAL_USDT} USDT"
    )

    print(
        f"Max Exposure      : "
        f"{MAX_EXPOSURE_USDT} USDT"
    )

    print(
        f"Order Size        : "
        f"{ORDER_SIZE_USDT} USDT"
    )

    print(
        f"Max Total Orders  : "
        f"{MAX_TOTAL_ORDERS}"
    )

    print(
        f"Max BUY Orders    : "
        f"{MAX_BUY_ORDERS}"
    )

    print(
        f"Max SELL Orders   : "
        f"{MAX_SELL_ORDERS}"
    )

    # --------------------------------------------------------
    # MARKET
    # --------------------------------------------------------

    price, atr = get_market_data()

    atr_percent = atr / price

    regime, grid_percent = (
        determine_regime(
            atr_percent
        )
    )

    print()
    print("=" * 72)
    print("MARKET STATE")
    print("=" * 72)

    print(
        f"BTC Price         : "
        f"${price:,.2f}"
    )

    print(
        f"ATR               : "
        f"${atr:,.2f}"
    )

    print(
        f"ATR / Price       : "
        f"{atr_percent * 100:.4f}%"
    )

    print(
        f"Volatility Regime : "
        f"{regime}"
    )

    print(
        f"Grid Distance     : "
        f"{grid_percent * 100:.4f}%"
    )

    # --------------------------------------------------------
    # OPEN ORDERS
    # --------------------------------------------------------

    manager = OrderManager()

    open_orders = (
        manager.get_open_orders()
    )

    (
        buy_orders,
        sell_orders,
        current_exposure,
    ) = calculate_risk(
        open_orders
    )

    print()
    print("=" * 72)
    print("CURRENT RISK")
    print("=" * 72)

    print(
        f"Open Orders       : "
        f"{len(open_orders)}"
    )

    print(
        f"BUY Orders        : "
        f"{buy_orders}"
    )

    print(
        f"SELL Orders       : "
        f"{sell_orders}"
    )

    print(
        f"Exposure          : "
        f"${current_exposure:,.2f}"
    )

    print(
        f"Remaining         : "
        f"${MAX_EXPOSURE_USDT - current_exposure:,.2f}"
    )

    # --------------------------------------------------------
    # SAFETY
    # --------------------------------------------------------

    if len(open_orders) > MAX_TOTAL_ORDERS:

        print()
        print(
            "!!! TOTAL ORDER LIMIT EXCEEDED !!!"
        )

        return

    if buy_orders > MAX_BUY_ORDERS:

        print()
        print(
            "!!! BUY LIMIT EXCEEDED !!!"
        )

        return

    if sell_orders > MAX_SELL_ORDERS:

        print()
        print(
            "!!! SELL LIMIT EXCEEDED !!!"
        )

        return

    if current_exposure > MAX_EXPOSURE_USDT:

        print()
        print(
            "!!! EXPOSURE LIMIT EXCEEDED !!!"
        )

        return

    # --------------------------------------------------------
    # AVAILABLE CAPACITY
    # --------------------------------------------------------

    remaining_exposure = (
        MAX_EXPOSURE_USDT
        - current_exposure
    )

    available_slots = int(
        remaining_exposure
        / ORDER_SIZE_USDT
    )

    available_total_slots = min(
        available_slots,
        MAX_TOTAL_ORDERS
        - len(open_orders),
    )

    print()
    print("=" * 72)
    print("AVAILABLE CAPACITY")
    print("=" * 72)

    print(
        f"Available Exposure : "
        f"${remaining_exposure:,.2f}"
    )

    print(
        f"Available Slots    : "
        f"{available_total_slots}"
    )

    # --------------------------------------------------------
    # BUILD GRID
    # --------------------------------------------------------

    grid = build_grid(
        price,
        grid_percent,
    )

    print()
    print("=" * 72)
    print("ADAPTIVE GRID")
    print("=" * 72)

    existing_count = 0
    missing_count = 0
    duplicate_count = 0

    for item in grid:

        matches = find_existing_orders(
            item,
            open_orders,
        )

        if matches:

            existing_count += 1

            print(
                f"[EXISTS]  "
                f"Level {item['level']:>3} | "
                f"{item['side'].upper():4} | "
                f"${item['price']:,.1f} | "
                f"Order "
                f"{matches[0].get('ordId')}"
            )

            if len(matches) > 1:

                duplicate_count += (
                    len(matches) - 1
                )

                print(
                    f"           "
                    f"!!! DUPLICATE: "
                    f"{len(matches)} orders !!!"
                )

        else:

            missing_count += 1

            print(
                f"[MISSING] "
                f"Level {item['level']:>3} | "
                f"{item['side'].upper():4} | "
                f"${item['price']:,.1f}"
            )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)

    print(
        f"Strategy Capital  : "
        f"${STRATEGY_CAPITAL_USDT:,.2f}"
    )

    print(
        f"Max Exposure      : "
        f"${MAX_EXPOSURE_USDT:,.2f}"
    )

    print(
        f"Volatility Regime : "
        f"{regime}"
    )

    print(
        f"Grid Distance     : "
        f"{grid_percent * 100:.4f}%"
    )

    print(
        f"Grid Levels       : "
        f"{len(grid)}"
    )

    print(
        f"Existing          : "
        f"{existing_count}"
    )

    print(
        f"Missing           : "
        f"{missing_count}"
    )

    print(
        f"Duplicates        : "
        f"{duplicate_count}"
    )

    print(
        f"Open Orders       : "
        f"{len(open_orders)}"
    )

    print(
        f"Current Exposure  : "
        f"${current_exposure:,.2f}"
    )

    print(
        f"Available Slots   : "
        f"{available_total_slots}"
    )

    print()

    if DRY_RUN:

        print(
            "DRY RUN: "
            "NO ORDERS WILL BE CREATED"
        )

        print(
            "DRY RUN: "
            "NO ORDERS WILL BE CANCELLED"
        )

    print()
    print("=" * 72)
    print("          ADAPTIVE GRID BOT v4.3 OK")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()