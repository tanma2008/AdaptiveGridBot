import os
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
import okx.MarketData as MarketData


# ============================================
# Configuration
# ============================================

load_dotenv()

FLAG = os.getenv("OKX_FLAG", "1")

INST_ID = "BTC-USDT"
BAR = "1H"
LIMIT = "500"


# ============================================
# OKX Market API
# ============================================

market = MarketData.MarketAPI(
    flag=FLAG,
    debug=False,
)


# ============================================
# Get Candles
# ============================================

def get_candles(
    inst_id=INST_ID,
    bar=BAR,
    limit=LIMIT,
):
    response = market.get_candlesticks(
        instId=inst_id,
        bar=bar,
        limit=limit,
    )

    if response.get("code") != "0":
        raise RuntimeError(
            f"OKX Market API Error: {response}"
        )

    return response["data"]


# ============================================
# Convert OKX Candles → DataFrame
# ============================================

def candles_to_dataframe(candles):

    columns = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "volCcy",
        "volCcyQuote",
        "confirm",
    ]

    df = pd.DataFrame(
        candles,
        columns=columns,
    )

    # Convert numbers
    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "volCcy",
        "volCcyQuote",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # Timestamp → datetime
    df["timestamp"] = pd.to_datetime(
        pd.to_numeric(df["timestamp"]),
        unit="ms",
        utc=True,
    )

    # Oldest → newest
    df = df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    return df


# ============================================
# Main
# ============================================

def main():

    print()
    print("=" * 70)
    print("             ADAPTIVE GRID BOT")
    print("                 MARKET DATA")
    print("=" * 70)

    print()
    print(f"Exchange : OKX Demo")
    print(f"Symbol   : {INST_ID}")
    print(f"Timeframe: {BAR}")
    print(f"Candles  : {LIMIT}")

    print()
    print("Downloading candles...")

    candles = get_candles()

    df = candles_to_dataframe(candles)

    print()
    print(f"Received : {len(df)} candles")

    print()
    print("Latest candles")
    print("-" * 70)

    display_columns = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    print(
        df[display_columns]
        .tail(10)
        .to_string(index=False)
    )

    print()
    print("=" * 70)
    print("              MARKET DATA OK")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()