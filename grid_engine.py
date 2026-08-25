import pandas as pd


# ============================================
# Configuration
# ============================================

FILE_1H = "btc_usdt_1h.csv"
FILE_1D = "btc_usdt_1d.csv"

ATR_MULTIPLIER = 0.3

GRID_LEVELS_UP = 3
GRID_LEVELS_DOWN = 5


# ============================================
# Indicators
# ============================================

def calculate_ema(df, period):

    return df["close"].ewm(
        span=period,
        adjust=False,
    ).mean()


def calculate_true_range(df):

    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]

    tr2 = (
        df["high"] - previous_close
    ).abs()

    tr3 = (
        df["low"] - previous_close
    ).abs()

    return pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)


def calculate_atr(df, period=30):

    true_range = calculate_true_range(df)

    return true_range.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()


# ============================================
# Trend
# ============================================

def determine_trend(row):

    price = row["close"]
    ema50 = row["ema50"]
    ema200 = row["ema200"]

    if price > ema50 and ema50 > ema200:
        return "UP"

    if price < ema50 and ema50 < ema200:
        return "DOWN"

    return "SIDEWAY"


# ============================================
# Build Grid
# ============================================

def build_grid(
    price,
    grid_distance,
    levels_up=3,
    levels_down=5,
):

    grid = []

    # Buy levels
    for level in range(
        1,
        levels_down + 1,
    ):

        grid.append({
            "level": -level,
            "side": "BUY",
            "price": price - (
                grid_distance * level
            ),
        })

    # Sell levels
    for level in range(
        1,
        levels_up + 1,
    ):

        grid.append({
            "level": level,
            "side": "SELL",
            "price": price + (
                grid_distance * level
            ),
        })

    return pd.DataFrame(grid)


# ============================================
# Main
# ============================================

def main():

    print()
    print("=" * 70)
    print("             ADAPTIVE GRID BOT")
    print("                 GRID ENGINE")
    print("=" * 70)

    # ----------------------------------------
    # Load data
    # ----------------------------------------

    df_1h = pd.read_csv(
        FILE_1H,
        parse_dates=["timestamp"],
    )

    df_1d = pd.read_csv(
        FILE_1D,
        parse_dates=["timestamp"],
    )

    # ----------------------------------------
    # Indicators
    # ----------------------------------------

    df_1h["ema50"] = calculate_ema(
        df_1h,
        50,
    )

    df_1h["ema200"] = calculate_ema(
        df_1h,
        200,
    )

    df_1d["atr30"] = calculate_atr(
        df_1d,
        30,
    )

    # ----------------------------------------
    # Latest market state
    # ----------------------------------------

    latest_1h = df_1h.iloc[-1]
    latest_1d = df_1d.iloc[-1]

    price = latest_1h["close"]

    ema50 = latest_1h["ema50"]
    ema200 = latest_1h["ema200"]

    atr30 = latest_1d["atr30"]

    trend = determine_trend(
        latest_1h
    )

    # ----------------------------------------
    # Adaptive Grid Distance
    # ----------------------------------------

    grid_distance = (
        atr30 * ATR_MULTIPLIER
    )

    # ----------------------------------------
    # Build grid
    # ----------------------------------------

    grid = build_grid(
        price=price,
        grid_distance=grid_distance,
        levels_up=GRID_LEVELS_UP,
        levels_down=GRID_LEVELS_DOWN,
    )

    # ----------------------------------------
    # Display
    # ----------------------------------------

    print()
    print("MARKET")
    print("-" * 70)

    print(
        f"BTC Price       : ${price:,.2f}"
    )

    print(
        f"EMA50 (1H)      : ${ema50:,.2f}"
    )

    print(
        f"EMA200 (1H)     : ${ema200:,.2f}"
    )

    print(
        f"Trend           : {trend}"
    )

    print()

    print(
        f"ATR30 (1D)      : ${atr30:,.2f}"
    )

    print(
        f"ATR Multiplier  : {ATR_MULTIPLIER}"
    )

    print(
        f"Grid Distance   : ${grid_distance:,.2f}"
    )

    print()
    print("GRID LEVELS")
    print("-" * 70)

    print(
        grid[
            [
                "level",
                "side",
                "price",
            ]
        ].to_string(
            index=False,
            formatters={
                "price": lambda x:
                    f"${x:,.2f}"
            },
        )
    )

    print()
    print("=" * 70)
    print("              GRID ENGINE OK")
    print("=" * 70)
    print()
    

if __name__ == "__main__":
    main()