import os
import csv
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import okx.Trade as Trade


load_dotenv()

API_KEY = os.getenv("OKX_API_KEY")
SECRET_KEY = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
FLAG = os.getenv("OKX_FLAG", "1")

if not API_KEY:
    raise RuntimeError("OKX_API_KEY is missing")

if not SECRET_KEY:
    raise RuntimeError("OKX_SECRET_KEY is missing")

if not PASSPHRASE:
    raise RuntimeError("OKX_PASSPHRASE is missing")


api = Trade.TradeAPI(
    api_key=API_KEY,
    api_secret_key=SECRET_KEY,
    passphrase=PASSPHRASE,
    flag=FLAG,
)


def main():

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)

    after = str(int(start.timestamp() * 1000))
    before = str(int(now.timestamp() * 1000))

    print()
    print("=" * 70)
    print("        OKX DEMO FILL REPORT v0.3")
    print("=" * 70)
    print()
    print("Mode   :", "DEMO" if FLAG == "1" else "LIVE")
    print("Symbol : BTC-USDT")
    print("From   :", start)
    print("To     :", now)
    print()

    response = api.get_fills_history(
        instType="SPOT",
        instId="BTC-USDT",
        after=after,
        before=before,
        limit="100",
    )

    if response.get("code") != "0":
        raise RuntimeError(
            "OKX API Error: " + str(response)
        )

    fills = response.get("data", [])

    fills.sort(
        key=lambda x: int(x.get("ts", "0"))
    )

    print("Total fills :", len(fills))
    print()

    buy_count = 0
    sell_count = 0

    buy_btc = 0.0
    sell_btc = 0.0

    buy_usdt = 0.0
    sell_usdt = 0.0

    fee_usdt = 0.0

    with open(
        "okx_demo_fills_24h.csv",
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "datetime",
            "tradeId",
            "ordId",
            "side",
            "fillPx",
            "fillSz",
            "fee",
            "feeCcy",
        ])

        for row in fills:

            ts = row.get("ts", "")
            dt = ""

            if ts:
                dt = datetime.fromtimestamp(
                    int(ts) / 1000,
                    timezone.utc,
                ).isoformat()

            side = row.get("side", "")
            px = float(row.get("fillPx", 0))
            sz = float(row.get("fillSz", 0))

            fee = abs(
                float(row.get("fee", 0))
            )

            fee_ccy = row.get(
                "feeCcy",
                "",
            )

            value = px * sz

            if side == "buy":

                buy_count += 1
                buy_btc += sz
                buy_usdt += value

            elif side == "sell":

                sell_count += 1
                sell_btc += sz
                sell_usdt += value

            if fee_ccy == "USDT":
                fee_usdt += fee

            writer.writerow([
                dt,
                row.get("tradeId", ""),
                row.get("ordId", ""),
                side,
                row.get("fillPx", ""),
                row.get("fillSz", ""),
                row.get("fee", ""),
                fee_ccy,
            ])

    print("=" * 70)
    print("TRADING")
    print("=" * 70)

    print("BUY fills       :", buy_count)
    print("SELL fills      :", sell_count)

    print(
        "Bought BTC      :",
        f"{buy_btc:.8f}",
    )

    print(
        "Sold BTC        :",
        f"{sell_btc:.8f}",
    )

    print(
        "BUY value       :",
        f"{buy_usdt:.6f}",
        "USDT",
    )

    print(
        "SELL value      :",
        f"{sell_usdt:.6f}",
        "USDT",
    )

    print(
        "USDT fees       :",
        f"{fee_usdt:.6f}",
        "USDT",
    )

    print()
    print("=" * 70)
    print("CASH FLOW")
    print("=" * 70)

    cash_flow = (
        sell_usdt
        - buy_usdt
        - fee_usdt
    )

    print(
        "SELL - BUY - FEE:",
        f"{cash_flow:.6f}",
        "USDT",
    )

    print()
    print("CSV saved : okx_demo_fills_24h.csv")

    print()
    print("=" * 70)
    print("REPORT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()