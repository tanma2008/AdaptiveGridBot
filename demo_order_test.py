import os
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

# เราทดลอง Strategy ด้วยทุนจำลอง 100 USDT
STRATEGY_CAPITAL = Decimal("100")

MAX_EXPOSURE = Decimal("0.30")

ATR_MULTIPLIER = Decimal("0.30")

GRID_LEVELS = 5


# ============================================================
# MARKET API
# ============================================================

market_api = MarketData.MarketAPI(
    flag=FLAG
)


# ============================================================
# CANDLES
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
            f"OKX Market Error: {response}"
        )

    rows = response["data"]

    rows.reverse()

    candles = []

    for row in rows:

        candles.append({
            "open": Decimal(row[1]),
            "high": Decimal(row[2]),
            "low": Decimal(row[3]),
            "close": Decimal(row[4]),
        })

    return candles


# ============================================================
# PRICE
# ============================================================

def get_price():

    response = market_api.get_ticker(
        instId=INST_ID
    )

    if response.get("code") != "0":

        raise RuntimeError(
            f"Ticker Error: {response}"
        )

    return Decimal(
        response["data"][0]["last"]
    )


# ============================================================
# EMA
# ============================================================

def calculate_ema(
    values,
    period,
):

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
# ATR30D
# ============================================================

def calculate_atr(
    candles,
    period=30,
):

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
                abs(
                    high
                    - previous_close
                ),
                abs(
                    low
                    - previous_close
                ),
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

def get_trend(candles):

    closes = [
        c["close"]
        for c in candles
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
# GRID 1
# ============================================================

def calculate_grid1(
    price,
    atr30d,
):

    distance = (
        atr30d
        * ATR_MULTIPLIER
    )

    grid1_price = (
        price
        - distance
    )

    max_exposure = (
        STRATEGY_CAPITAL
        * MAX_EXPOSURE
    )

    base_size = (
        max_exposure
        / Decimal(str(GRID_LEVELS))
    )

    # UP = 0.8 multiplier
    size = (
        base_size
        * Decimal("0.80")
    )

    return (
        distance,
        grid1_price,
        size,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print("       ADAPTIVE GRID BOT - FIRST DEMO ORDER")
    print("=" * 72)

    print()
    print(
        "WARNING: ONE LIMIT BUY ONLY"
    )

    print(
        "Strategy Capital : "
        f"{STRATEGY_CAPITAL:.2f} USDT"
    )

    print(
        "Max Exposure     : "
        f"{STRATEGY_CAPITAL * MAX_EXPOSURE:.2f} USDT"
    )

    print()

    # --------------------------------------------------------
    # Get market data
    # --------------------------------------------------------

    candles_1h = get_candles(
        "1H",
        300,
    )

    candles_1d = get_candles(
        "1D",
        100,
    )

    price = get_price()

    trend, ema50, ema200 = (
        get_trend(
            candles_1h
        )
    )

    atr30d = calculate_atr(
        candles_1d,
        30,
    )

    distance, grid1, size = (
        calculate_grid1(
            price,
            atr30d,
        )
    )

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print(
        f"BTC Price       : "
        f"${price:,.2f}"
    )

    print(
        f"EMA50 (1H)      : "
        f"${ema50:,.2f}"
    )

    print(
        f"EMA200 (1H)     : "
        f"${ema200:,.2f}"
    )

    print(
        f"Trend           : "
        f"{trend}"
    )

    print()

    print(
        f"ATR30D (1D)     : "
        f"${atr30d:,.2f}"
    )

    print(
        f"Grid Distance   : "
        f"${distance:,.2f}"
    )

    print()

    print(
        f"Grid 1 BUY      : "
        f"${grid1:,.2f}"
    )

    print(
        f"Order Size      : "
        f"{size:.2f} USDT"
    )

    # --------------------------------------------------------
    # Safety
    # --------------------------------------------------------

    if trend != "UP":

        print()
        print(
            "STOP"
        )

        print(
            f"Trend is {trend}."
        )

        print(
            "First test BUY is only "
            "allowed in UP trend."
        )

        return

    if size > (
        STRATEGY_CAPITAL
        * MAX_EXPOSURE
    ):

        print()
        print(
            "STOP: Risk limit exceeded."
        )

        return

    # --------------------------------------------------------
    # Order manager
    # --------------------------------------------------------

    manager = OrderManager()

    open_orders = (
        manager.get_open_orders()
    )

    print()

    print(
        f"Existing Orders : "
        f"{len(open_orders)}"
    )

    if open_orders:

        print()
        print(
            "STOP: Existing orders detected."
        )

        print(
            "No new order will be sent."
        )

        return

    # --------------------------------------------------------
    # FINAL CONFIRMATION
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("                    ORDER")
    print("=" * 72)

    print()

    print(
        "Exchange : OKX DEMO"
    )

    print(
        "Symbol   : BTC-USDT"
    )

    print(
        "Side     : BUY"
    )

    print(
        f"Price    : ${grid1:,.2f}"
    )

    print(
        f"Size     : {size:.2f} USDT"
    )

    print()

    answer = input(
        "SEND ONE DEMO ORDER? Type YES: "
    )

    if answer.strip() != "YES":

        print()
        print(
            "Cancelled. No order sent."
        )

        return

    # --------------------------------------------------------
    # SEND
    # --------------------------------------------------------

    print()
    print(
        "Sending order..."
    )

    response = (
        manager.place_limit_order(
            side="buy",
            price=grid1,
            usdt_size=size,
        )
    )

    print()
    print("=" * 72)
    print("                 ORDER RESPONSE")
    print("=" * 72)

    print()

    print(response)

    print()
    print("=" * 72)
    print("              DEMO ORDER COMPLETE")
    print("=" * 72)


if __name__ == "__main__":

    main()