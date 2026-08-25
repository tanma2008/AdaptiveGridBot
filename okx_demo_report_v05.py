import os
import sys
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext

from dotenv import load_dotenv
import okx.Trade as Trade


getcontext().prec = 28

# ============================================================
# OKX DEMO REPORT v0.5
# READ ONLY
# BTC-USDT
#
# Usage:
#   python okx_demo_report_v05.py
#   python okx_demo_report_v05.py 1
#   python okx_demo_report_v05.py 3
# ============================================================

load_dotenv()

API_KEY = os.getenv("OKX_API_KEY")
SECRET_KEY = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
FLAG = os.getenv("OKX_FLAG", "1")

INST_TYPE = "SPOT"
INST_ID = "BTC-USDT"
LIMIT = 100


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


def D(value):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def get_hours():

    if len(sys.argv) < 2:
        return 3

    try:
        hours = int(sys.argv[1])
    except ValueError:
        raise RuntimeError(
            "Usage: python okx_demo_report_v05.py [hours]"
        )

    if hours < 1 or hours > 24:
        raise RuntimeError(
            "Hours must be between 1 and 24"
        )

    return hours


def utc_from_ms(ts):

    return datetime.fromtimestamp(
        int(ts) / 1000,
        timezone.utc,
    )


def fill_key(row):

    return (
        row.get("tradeId")
        or row.get("fillId")
        or (
            row.get("ordId"),
            row.get("ts"),
            row.get("side"),
            row.get("fillPx"),
            row.get("fillSz"),
        )
    )


def get_all_fills():

    result = []
    seen = set()

    response = api.get_fills_history(
        instType=INST_TYPE,
        instId=INST_ID,
        limit=str(LIMIT),
    )

    if response.get("code") != "0":
        raise RuntimeError(
            "OKX API Error: " + str(response)
        )

    rows = response.get("data", [])

    while rows:

        for row in rows:

            key = fill_key(row)

            if key not in seen:
                seen.add(key)
                result.append(row)

        if len(rows) < LIMIT:
            break

        timestamps = [
            int(row["ts"])
            for row in rows
            if row.get("ts")
        ]

        if not timestamps:
            break

        oldest = min(timestamps)

        response = api.get_fills_history(
            instType=INST_TYPE,
            instId=INST_ID,
            before=str(oldest),
            limit=str(LIMIT),
        )

        if response.get("code") != "0":
            raise RuntimeError(
                "OKX API Error: " + str(response)
            )

        new_rows = response.get("data", [])

        if not new_rows:
            break

        old_count = len(result)

        for row in new_rows:

            key = fill_key(row)

            if key not in seen:
                seen.add(key)
                result.append(row)

        if len(result) == old_count:
            break

        rows = new_rows

    return result


def filter_period(fills, hours):

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)

    start_ms = int(
        start.timestamp() * 1000
    )

    end_ms = int(
        now.timestamp() * 1000
    )

    selected = []

    for row in fills:

        ts = row.get("ts")

        if not ts:
            continue

        value = int(ts)

        if start_ms <= value <= end_ms:
            selected.append(row)

    selected.sort(
        key=lambda x: int(x.get("ts", "0"))
    )

    return selected, start, now


def analyze(fills):

    buy_count = 0
    sell_count = 0

    buy_btc = D("0")
    sell_btc = D("0")

    buy_value = D("0")
    sell_value = D("0")

    btc_fee = D("0")
    usdt_fee = D("0")

    for row in fills:

        side = row.get(
            "side",
            "",
        ).lower()

        price = D(
            row.get("fillPx")
        )

        size = D(
            row.get("fillSz")
        )

        value = price * size

        fee = abs(
            D(row.get("fee"))
        )

        fee_ccy = row.get(
            "feeCcy",
            "",
        ).upper()

        if side == "buy":

            buy_count += 1
            buy_btc += size
            buy_value += value

        elif side == "sell":

            sell_count += 1
            sell_btc += size
            sell_value += value

        if fee_ccy == "BTC":
            btc_fee += fee

        elif fee_ccy == "USDT":
            usdt_fee += fee

    return {
        "buy_count": buy_count,
        "sell_count": sell_count,
        "buy_btc": buy_btc,
        "sell_btc": sell_btc,
        "buy_value": buy_value,
        "sell_value": sell_value,
        "btc_fee": btc_fee,
        "usdt_fee": usdt_fee,
    }


def match_cycles(fills):

    inventory = []
    cycles = []

    for row in fills:

        side = row.get(
            "side",
            "",
        ).lower()

        price = D(
            row.get("fillPx")
        )

        size = D(
            row.get("fillSz")
        )

        fee = abs(
            D(row.get("fee"))
        )

        fee_ccy = row.get(
            "feeCcy",
            "",
        ).upper()

        ts = int(
            row.get("ts", "0")
        )

        if side == "buy":

            net_qty = size

            if fee_ccy == "BTC":
                net_qty -= fee

            inventory.append({
                "ts": ts,
                "price": price,
                "qty": net_qty,
                "ordId": row.get(
                    "ordId",
                    "",
                ),
            })

        elif side == "sell":

            remaining = size

            if fee_ccy == "BTC":
                remaining -= fee

            while remaining > 0 and inventory:

                buy = inventory[0]

                matched = min(
                    remaining,
                    buy["qty"],
                )

                gross = (
                    price - buy["price"]
                ) * matched

                sell_fee = D("0")

                if fee_ccy == "USDT":

                    if size > 0:
                        sell_fee = (
                            fee
                            * matched
                            / size
                        )

                net = (
                    gross
                    - sell_fee
                )

                cycles.append({
                    "buy_ts": buy["ts"],
                    "sell_ts": ts,
                    "buy_price": buy["price"],
                    "sell_price": price,
                    "qty": matched,
                    "gross": gross,
                    "fee": sell_fee,
                    "net": net,
                })

                buy["qty"] -= matched
                remaining -= matched

                if buy["qty"] <= 0:
                    inventory.pop(0)

    return cycles, inventory


def save_csv(fills, cycles, hours):

    fill_file = (
        f"okx_demo_fills_{hours}h_v05.csv"
    )

    cycle_file = (
        f"okx_demo_cycles_{hours}h_v05.csv"
    )

    with open(
        fill_file,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "datetime_utc",
            "tradeId",
            "ordId",
            "side",
            "fillPx",
            "fillSz",
            "fee",
            "feeCcy",
            "ts",
        ])

        for row in fills:

            ts = row.get("ts", "")

            dt = ""

            if ts:
                dt = utc_from_ms(ts).isoformat()

            writer.writerow([
                dt,
                row.get("tradeId", ""),
                row.get("ordId", ""),
                row.get("side", ""),
                row.get("fillPx", ""),
                row.get("fillSz", ""),
                row.get("fee", ""),
                row.get("feeCcy", ""),
                ts,
            ])

    with open(
        cycle_file,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "buy_time",
            "sell_time",
            "buy_price",
            "sell_price",
            "qty_btc",
            "gross_pnl",
            "sell_fee",
            "net_pnl",
        ])

        for cycle in cycles:

            writer.writerow([
                utc_from_ms(
                    cycle["buy_ts"]
                ).isoformat(),

                utc_from_ms(
                    cycle["sell_ts"]
                ).isoformat(),

                cycle["buy_price"],
                cycle["sell_price"],
                cycle["qty"],
                cycle["gross"],
                cycle["fee"],
                cycle["net"],
            ])

    return fill_file, cycle_file


def main():

    hours = get_hours()

    print()
    print("=" * 76)
    print("        OKX DEMO PERFORMANCE REPORT v0.5")
    print("             BTC-USDT / LAST PERIOD")
    print("=" * 76)

    print()
    print(
        "Mode       :",
        "DEMO" if FLAG == "1" else "LIVE",
    )

    print(
        "Symbol     :",
        INST_ID,
    )

    print(
        "Period     :",
        f"LAST {hours} HOUR"
        if hours == 1
        else f"LAST {hours} HOURS",
    )

    print()
    print("Loading fills from OKX...")

    all_fills = get_all_fills()

    fills, start, now = filter_period(
        all_fills,
        hours,
    )

    result = analyze(fills)

    cycles, inventory = match_cycles(
        fills
    )

    wins = [
        x for x in cycles
        if x["net"] > 0
    ]

    losses = [
        x for x in cycles
        if x["net"] < 0
    ]

    realized = sum(
        (
            x["net"]
            for x in cycles
        ),
        D("0"),
    )

    gross_profit = sum(
        (
            x["net"]
            for x in wins
        ),
        D("0"),
    )

    gross_loss = abs(
        sum(
            (
                x["net"]
                for x in losses
            ),
            D("0"),
        )
    )

    if gross_loss > 0:
        profit_factor = (
            gross_profit
            / gross_loss
        )
    else:
        profit_factor = None

    if cycles:
        win_rate = (
            Decimal(len(wins))
            / Decimal(len(cycles))
            * Decimal("100")
        )
    else:
        win_rate = D("0")

    open_btc = sum(
        (
            x["qty"]
            for x in inventory
        ),
        D("0"),
    )

    print()
    print("=" * 76)
    print("PERIOD")
    print("=" * 76)

    print(
        "From       :",
        start,
    )

    print(
        "To         :",
        now,
    )

    print(
        "Fills fetched     :",
        len(all_fills),
    )

    print(
        "Fills in period   :",
        len(fills),
    )

    print()
    print("=" * 76)
    print("TRADING ACTIVITY")
    print("=" * 76)

    print(
        "BUY fills         :",
        result["buy_count"],
    )

    print(
        "SELL fills        :",
        result["sell_count"],
    )

    print(
        "Bought BTC        :",
        f"{result['buy_btc']:.8f}",
    )

    print(
        "Sold BTC          :",
        f"{result['sell_btc']:.8f}",
    )

    print(
        "BUY value         :",
        f"{result['buy_value']:.6f}",
        "USDT",
    )

    print(
        "SELL value        :",
        f"{result['sell_value']:.6f}",
        "USDT",
    )

    print()
    print("=" * 76)
    print("FEES")
    print("=" * 76)

    print(
        "BTC fee           :",
        f"{result['btc_fee']:.8f}",
        "BTC",
    )

    print(
        "USDT fee          :",
        f"{result['usdt_fee']:.8f}",
        "USDT",
    )

    print()
    print("=" * 76)
    print("GRID PERFORMANCE")
    print("=" * 76)

    print(
        "Completed cycles  :",
        len(cycles),
    )

    print(
        "Winning cycles    :",
        len(wins),
    )

    print(
        "Losing cycles     :",
        len(losses),
    )

    print(
        "Win rate          :",
        f"{win_rate:.2f}%",
    )

    print(
        "Realized P/L      :",
        f"{realized:.6f}",
        "USDT",
    )

    if profit_factor is None:

        print(
            "Profit factor     : INF"
        )

    else:

        print(
            "Profit factor     :",
            f"{profit_factor:.4f}",
        )

    if cycles:

        avg = (
            realized
            / Decimal(len(cycles))
        )

        best = max(
            x["net"]
            for x in cycles
        )

        worst = min(
            x["net"]
            for x in cycles
        )

        print(
            "Avg cycle P/L     :",
            f"{avg:.6f}",
            "USDT",
        )

        print(
            "Best cycle        :",
            f"{best:.6f}",
            "USDT",
        )

        print(
            "Worst cycle       :",
            f"{worst:.6f}",
            "USDT",
        )

    print()
    print("=" * 76)
    print("OPEN INVENTORY")
    print("=" * 76)

    print(
        "Unmatched BUY BTC :",
        f"{open_btc:.8f}",
    )

    print()
    print("=" * 76)
    print("SAVING")
    print("=" * 76)

    fill_file, cycle_file = save_csv(
        fills,
        cycles,
        hours,
    )

    print(
        "Fills CSV         :",
        fill_file,
    )

    print(
        "Cycles CSV        :",
        cycle_file,
    )

    print()
    print("=" * 76)
    print("REPORT COMPLETE")
    print("=" * 76)

    print()
    print(
        "READ ONLY - NO ORDERS CREATED"
    )

    print(
        "READ ONLY - NO ORDERS CANCELLED"
    )

    print()


if __name__ == "__main__":
    main()