import os
import time
from decimal import Decimal

from dotenv import load_dotenv

import okx.MarketData as MarketData

from order_manager import OrderManager


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

FLAG = os.getenv("OKX_FLAG", "1")

INST_ID = "BTC-USDT"

# True  = วิเคราะห์อย่างเดียว
# False = อนุญาตเข้าสู่ Demo order logic
DRY_RUN = True

CHECK_INTERVAL = 60

MAX_EXPOSURE = Decimal("0.30")

ATR_MULTIPLIER = Decimal("0.30")

GRID_BUY_LEVELS = 5
GRID_SELL_LEVELS = 3


# ============================================================
# OKX MARKET API
# ============================================================

market_api = MarketData.MarketAPI(
    flag=FLAG
)


# ============================================================
# MARKET PRICE
# ============================================================

def get_price():

    response = market_api.get_ticker(
        instId=INST_ID
    )

    if response.get("code") != "0":

        raise RuntimeError(
            f"Ticker API Error: {response}"
        )

    return Decimal(
        response["data"][0]["last"]
    )


# ============================================================
# GET CANDLES
# ============================================================

def get_candles(
    timeframe,
    limit=300,
):

    response = market_api.get_candlesticks(
        instId=INST_ID,
        bar=timeframe,
        limit=str(limit),
    )

    if response.get("code") != "0":

        raise RuntimeError(
            f"Candle API Error: {response}"
        )

    rows = response["data"]

    rows.reverse()

    candles = []

    for row in rows:

        candles.append({
            "ts": int(row[0]),
            "open": Decimal(row[1]),
            "high": Decimal(row[2]),
            "low": Decimal(row[3]),
            "close": Decimal(row[4]),
            "volume": Decimal(row[5]),
        })

    return candles


# ============================================================
# EMA
# ============================================================

def calculate_ema(
    values,
    period,
):

    if len(values) < period:

        raise RuntimeError(
            f"Need at least {period} candles"
        )

    multiplier = (
        Decimal("2")
        / Decimal(str(period + 1))
    )

    result = values[0]

    for value in values[1:]:

        result = (
            (value - result)
            * multiplier
            + result
        )

    return result


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles,
    period=30,
):

    if len(candles) < period + 1:

        raise RuntimeError(
            "Not enough candles for ATR"
        )

    true_ranges = []

    previous_close = None

    for candle in candles:

        high = candle["high"]
        low = candle["low"]
        close = candle["close"]

        if previous_close is None:

            tr = high - low

        else:

            tr = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

        true_ranges.append(tr)

        previous_close = close

    recent = true_ranges[-period:]

    return (
        sum(recent)
        / Decimal(str(period))
    )


# ============================================================
# TREND
# ============================================================

def calculate_trend(
    candles,
):

    closes = [
        candle["close"]
        for candle in candles
    ]

    ema50 = calculate_ema(
        closes,
        50,
    )

    ema200 = calculate_ema(
        closes,
        200,
    )

    price = closes[-1]

    if (
        price > ema50
        and ema50 > ema200
    ):

        trend = "UP"

    elif (
        price < ema50
        and ema50 < ema200
    ):

        trend = "DOWN"

    else:

        trend = "SIDEWAY"

    return (
        trend,
        ema50,
        ema200,
    )


# ============================================================
# GRID
# ============================================================

def build_grid(
    price,
    atr30d,
    trend,
):

    distance = (
        atr30d
        * ATR_MULTIPLIER
    )

    # --------------------------------------------------------
    # Position multipliers
    # --------------------------------------------------------

    if trend == "UP":

        multipliers = [
            Decimal("0.80"),
            Decimal("1.00"),
            Decimal("1.20"),
            Decimal("1.40"),
            Decimal("1.60"),
        ]

    elif trend == "SIDEWAY":

        multipliers = [
            Decimal("1.00"),
            Decimal("1.00"),
            Decimal("1.00"),
            Decimal("1.00"),
            Decimal("1.00"),
        ]

    else:

        multipliers = [
            Decimal("1.00"),
            Decimal("0.80"),
            Decimal("0.60"),
            Decimal("0.40"),
            Decimal("0.20"),
        ]

    # --------------------------------------------------------
    # Base sizing
    #
    # NOTE:
    # For now this is the Demo reference capital.
    # Before automatic order submission we will replace
    # this with real OKX available balance.
    # --------------------------------------------------------

    demo_capital = Decimal("100")

    max_exposure = (
        demo_capital
        * MAX_EXPOSURE
    )

    base_size = (
        max_exposure
        / Decimal(
            str(GRID_BUY_LEVELS)
        )
    )

    buys = []

    for index in range(
        GRID_BUY_LEVELS
    ):

        level = index + 1

        order_price = (
            price
            - distance * level
        )

        size = (
            base_size
            * multipliers[index]
        )

        buys.append({
            "level": -level,
            "price": order_price,
            "size": size,
        })

    sells = []

    for index in range(
        GRID_SELL_LEVELS
    ):

        level = index + 1

        order_price = (
            price
            + distance * level
        )

        sells.append({
            "level": level,
            "price": order_price,
        })

    return (
        distance,
        buys,
        sells,
    )


# ============================================================
# DISPLAY
# ============================================================

def print_status(
    price,
    trend,
    ema50,
    ema200,
    atr30d,
    distance,
    buys,
    sells,
    open_orders,
):

    print()
    print("=" * 72)
    print("             ADAPTIVE GRID BOT - DEMO")
    print("=" * 72)

    print()

    print(
        f"Exchange       : "
        f"{'OKX DEMO' if FLAG == '1' else 'OKX LIVE'}"
    )

    print(
        f"Symbol         : {INST_ID}"
    )

    print()

    print(
        f"BTC Price      : ${price:,.2f}"
    )

    print()

    print(
        f"EMA50 (1H)     : ${ema50:,.2f}"
    )

    print(
        f"EMA200 (1H)    : ${ema200:,.2f}"
    )

    print(
        f"Trend (1H)     : {trend}"
    )

    print()

    print(
        f"ATR30D (1D)    : ${atr30d:,.2f}"
    )

    print(
        f"ATR30D %       : "
        f"{(atr30d / price * Decimal('100')):.2f}%"
    )

    print(
        f"Grid Distance  : ${distance:,.2f}"
    )

    print()

    print("PROPOSED BUY ORDERS")
    print("-" * 72)

    for order in buys:

        print(
            f"Grid {abs(order['level'])} "
            f"| BUY  "
            f"${order['price']:,.2f} "
            f"| {order['size']:.2f} USDT"
        )

    print()

    print("PROPOSED SELL ORDERS")
    print("-" * 72)

    for order in sells:

        print(
            f"Grid {order['level']} "
            f"| SELL "
            f"${order['price']:,.2f}"
        )

    print()

    print(
        f"Existing OKX Orders : "
        f"{len(open_orders)}"
    )

    print()

    if DRY_RUN:

        print(
            "MODE             : DRY RUN"
        )

        print(
            "NO ORDERS SENT"
        )

    else:

        print(
            "MODE             : DEMO TRADING"
        )

    print("=" * 72)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print("       ADAPTIVE GRID BOT - DEMO STARTING")
    print("=" * 72)

    print()

    print(
        f"DRY RUN          : {DRY_RUN}"
    )

    print(
        f"Check interval   : {CHECK_INTERVAL} sec"
    )

    print(
        "Trend timeframe  : 1H"
    )

    print(
        "ATR timeframe    : 1D"
    )

    print()

    manager = OrderManager()

    while True:

        try:

            # ------------------------------------------------
            # 1H = Trend
            # ------------------------------------------------

            candles_1h = get_candles(
                "1H",
                300,
            )

            # ------------------------------------------------
            # 1D = ATR30D
            # ------------------------------------------------

            candles_1d = get_candles(
                "1D",
                100,
            )

            price = get_price()

            trend, ema50, ema200 = (
                calculate_trend(
                    candles_1h
                )
            )

            atr30d = calculate_atr(
                candles_1d,
                30,
            )

            distance, buys, sells = (
                build_grid(
                    price,
                    atr30d,
                    trend,
                )
            )

            open_orders = (
                manager.get_open_orders()
            )

            print_status(
                price=price,
                trend=trend,
                ema50=ema50,
                ema200=ema200,
                atr30d=atr30d,
                distance=distance,
                buys=buys,
                sells=sells,
                open_orders=open_orders,
            )

            # ------------------------------------------------
            # DEMO ORDER SUBMISSION
            # ------------------------------------------------

            if not DRY_RUN:

                print()
                print(
                    "DEMO ORDER MODE"
                )

                print(
                    "Order submission "
                    "is intentionally locked "
                    "in this build."
                )

        except KeyboardInterrupt:

            print()
            print(
                "Bot stopped by user."
            )

            break

        except Exception as e:

            print()
            print(
                "ERROR:"
            )

            print(
                repr(e)
            )

            print(
                "Retrying..."
            )

        print()

        print(
            f"Next check in "
            f"{CHECK_INTERVAL} seconds..."
        )

        time.sleep(
            CHECK_INTERVAL
        )


if __name__ == "__main__":

    main()