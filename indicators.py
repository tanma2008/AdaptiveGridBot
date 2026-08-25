import pandas as pd


# ============================================
# EMA
# ============================================

def calculate_ema(df, period):

    return df["close"].ewm(
        span=period,
        adjust=False,
    ).mean()


# ============================================
# True Range
# ============================================

def calculate_true_range(df):

    previous_close = df["close"].shift(1)

    range_1 = df["high"] - df["low"]

    range_2 = (
        df["high"] - previous_close
    ).abs()

    range_3 = (
        df["low"] - previous_close
    ).abs()

    true_range = pd.concat(
        [
            range_1,
            range_2,
            range_3,
        ],
        axis=1,
    ).max(axis=1)

    return true_range


# ============================================
# ATR
# ============================================

def calculate_atr(df, period=30):

    true_range = calculate_true_range(df)

    atr = true_range.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    return atr


# ============================================
# Add Indicators
# ============================================

def add_indicators(df):

    df = df.copy()

    df["ema50"] = calculate_ema(
        df,
        50,
    )

    df["ema200"] = calculate_ema(
        df,
        200,
    )

    df["atr30"] = calculate_atr(
        df,
        30,
    )

    return df


# ============================================
# Determine Trend
# ============================================

def determine_trend(row):

    price = row["close"]
    ema50 = row["ema50"]
    ema200 = row["ema200"]

    if (
        price > ema50
        and ema50 > ema200
    ):
        return "UP"

    if (
        price < ema50
        and ema50 < ema200
    ):
        return "DOWN"

    return "SIDEWAY"


# ============================================
# Main
# ============================================

if __name__ == "__main__":

    from market_data import (
        get_candles,
        candles_to_dataframe,
    )

    print()
    print("=" * 70)
    print("          ADAPTIVE GRID BOT")
    print("             INDICATORS")
    print("=" * 70)

    print()
    print("Downloading market data...")

    candles = get_candles(
        inst_id="BTC-USDT",
        bar="1H",
        limit="500",
    )

    df = candles_to_dataframe(
        candles
    )

    print(
        f"Received : {len(df)} candles"
    )

    # Calculate indicators
    df = add_indicators(df)

    # Latest row
    latest = df.iloc[-1]

    trend = determine_trend(
        latest
    )

    print()
    print("CURRENT MARKET")
    print("-" * 70)

    print(
        f"Time       : {latest['timestamp']}"
    )

    print(
        f"BTC Price  : ${latest['close']:,.2f}"
    )

    print(
        f"EMA50      : ${latest['ema50']:,.2f}"
    )

    print(
        f"EMA200     : ${latest['ema200']:,.2f}"
    )

    print(
        f"ATR30      : ${latest['atr30']:,.2f}"
    )

    print(
        f"ATR %      : "
        f"{latest['atr30'] / latest['close'] * 100:.2f}%"
    )

    print()
    print(
        f"TREND      : {trend}"
    )

    print()
    print("LATEST 10")
    print("-" * 70)

    display_columns = [
        "timestamp",
        "close",
        "ema50",
        "ema200",
        "atr30",
    ]

    print(
        df[display_columns]
        .tail(10)
        .to_string(index=False)
    )

    print()
    print("=" * 70)
    print("             INDICATORS OK")
    print("=" * 70)
    print()