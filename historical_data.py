import os
import time
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
import okx.MarketData as MarketData


# ============================================
# Configuration
# ============================================

load_dotenv()

FLAG = os.getenv("OKX_FLAG", "1")

INST_ID = "BTC-USDT"

# จำนวนแท่งที่ต้องการ
TARGET_CANDLES = 3000

# OKX limit ต่อ request
BATCH_SIZE = 300


# ============================================
# OKX Market API
# ============================================

market = MarketData.MarketAPI(
    flag=FLAG,
    debug=False,
)


# ============================================
# Convert candles
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

    df["timestamp"] = pd.to_datetime(
        pd.to_numeric(df["timestamp"]),
        unit="ms",
        utc=True,
    )

    return df


# ============================================
# Download historical candles
# ============================================

def download_history(
    inst_id=INST_ID,
    bar="1H",
    target_candles=TARGET_CANDLES,
):

    all_candles = []

    # ใช้ "after" เพื่อขอข้อมูลที่เก่าลงเรื่อย ๆ
    after = None

    print()
    print("=" * 70)
    print("        ADAPTIVE GRID BOT - HISTORICAL DATA")
    print("=" * 70)

    print()
    print(f"Symbol       : {inst_id}")
    print(f"Timeframe    : {bar}")
    print(f"Target       : {target_candles:,} candles")
    print()

    while len(all_candles) < target_candles:

        params = {
            "instId": inst_id,
            "bar": bar,
            "limit": str(BATCH_SIZE),
        }

        if after is not None:
            params["after"] = after

        response = market.get_candlesticks(**params)

        if response.get("code") != "0":
            raise RuntimeError(
                f"OKX API Error: {response}"
            )

        batch = response.get("data", [])

        if not batch:
            print("No more data returned.")
            break

        all_candles.extend(batch)

        # หา timestamp ที่เก่าที่สุดของ batch
        timestamps = [
            int(row[0])
            for row in batch
        ]

        oldest_timestamp = min(timestamps)

        after = str(oldest_timestamp)

        print(
            f"Downloaded : "
            f"{len(all_candles):,} candles"
            f" | oldest = "
            f"{datetime.fromtimestamp(oldest_timestamp / 1000)}"
        )

        # ป้องกันยิง API เร็วเกินไป
        time.sleep(0.2)

        # ถ้าได้ไม่เต็ม batch แปลว่าอาจไม่มีข้อมูลเก่ากว่านี้
        if len(batch) < BATCH_SIZE:
            print("Reached available history.")
            break

    # Convert
    df = candles_to_dataframe(
        all_candles
    )

    # Remove duplicates
    df = df.drop_duplicates(
        subset=["timestamp"]
    )

    # Oldest → newest
    df = df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    # จำกัดจำนวนตาม target
    if len(df) > target_candles:
        df = df.tail(
            target_candles
        ).reset_index(drop=True)

    return df


# ============================================
# Save
# ============================================

def save_data(
    df,
    filename,
):

    df.to_csv(
        filename,
        index=False,
    )

    print()
    print(
        f"Saved: {filename}"
    )


# ============================================
# Main
# ============================================

def main():

    # ----------------------------------------
    # 1H
    # ----------------------------------------

    df_1h = download_history(
        inst_id="BTC-USDT",
        bar="1H",
        target_candles=3000,
    )

    save_data(
        df_1h,
        "btc_usdt_1h.csv",
    )

    # ----------------------------------------
    # 1D
    # ----------------------------------------

    df_1d = download_history(
        inst_id="BTC-USDT",
        bar="1D",
        target_candles=500,
    )

    save_data(
        df_1d,
        "btc_usdt_1d.csv",
    )

    # ----------------------------------------
    # Summary
    # ----------------------------------------

    print()
    print("=" * 70)
    print("                 DOWNLOAD COMPLETE")
    print("=" * 70)

    print()

    print("1H DATA")
    print("-" * 70)
    print(f"Candles : {len(df_1h):,}")
    print(f"From    : {df_1h['timestamp'].iloc[0]}")
    print(f"To      : {df_1h['timestamp'].iloc[-1]}")

    print()

    print("1D DATA")
    print("-" * 70)
    print(f"Candles : {len(df_1d):,}")
    print(f"From    : {df_1d['timestamp'].iloc[0]}")
    print(f"To      : {df_1d['timestamp'].iloc[-1]}")

    print()
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()