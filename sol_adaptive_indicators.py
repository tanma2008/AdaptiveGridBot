import pandas as pd


# ============================================
# Configuration
# ============================================

FILE_1H = "sol_usdt_1h.csv"
FILE_1D = "sol_usdt_1d.csv"


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


# ============================================
# ATR
# ============================================

def calculate_atr(df, period=30):

    true_range = calculate_true_range(df)

    return true_range.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()


# ============================================
# Load data
# ============================================

def load_data():

    df_1h = pd.read_csv(
        FILE_1H,
        parse_dates=["timestamp"],
    )

    df_1d = pd.read_csv(
        FILE_1D,
        parse_dates=["timestamp"],
    )

    return df_1h, df_1d


# ============================================
# Add indicators
# ============================================

def build_indicators():

    df_1h, df_1d = load_data()

    # 1H trend indicators
    df_1h["ema50"] = calculate_ema(
        df_1h,
        50,
    )

    df_1h["ema200"] = calculate_ema(
        df_1h,
        200,
    )

    # Daily volatility
    df_1d["atr30"] = calculate_atr(
        df_1d,
        30,
    )

    return df_1h, df_1d


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
# Main
# ============================================

def main():

    print()
    print("=" * 70)
    print("        ADAPTIVE GRID BOT")
    print("          ADAPTIVE INDICATORS")
    print("=" * 70)

    print()
    print("Loading historical data...")

    df_1h, df_1d = build_indicators()

    latest_1h = df_1h.iloc[-1]
    latest_1d = df_1d.iloc[-1]

    trend = determine_trend(
        latest_1h
    )

    price = latest_1h["close"]

    atr30 = latest_1d["atr30"]

    atr_percent = (
        atr30 / price * 100
    )

    print()
    print("MARKET STATE")
    print("-" * 70)

    print(
        f"SOL Price       : ${price:,.2f}"
    )

    print(
        f"EMA50 (1H)      : "
        f"${latest_1h['ema50']:,.2f}"
    )

    print(
        f"EMA200 (1H)     : "
        f"${latest_1h['ema200']:,.2f}"
    )

    print(
        f"Trend (1H)      : {trend}"
    )

    print()

    print(
        f"ATR30 (1D)      : "
        f"${atr30:,.2f}"
    )

    print(
        f"ATR30 %         : "
        f"{atr_percent:.2f}%"
    )

    print()
    print("=" * 70)
    print("             INDICATORS READY")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()