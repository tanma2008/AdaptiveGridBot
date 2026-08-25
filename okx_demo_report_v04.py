import os
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext

from dotenv import load_dotenv
import okx.Trade as Trade


getcontext().prec = 28

# ============================================================
# OKX DEMO REPORT v0.4
# READ ONLY
# BTC-USDT / LAST 24 HOURS
# ============================================================

load_dotenv()

API_KEY = os.getenv("OKX_API_KEY")
SECRET_KEY = os.getenv("OKX_SECRET_KEY")
PASSPHRASE = os.getenv("OKX_PASSPHRASE")
FLAG = os.getenv("OKX_FLAG", "1")

INST_TYPE = "SPOT"
INST_ID = "BTC-USDT"
LIMIT = 100


# ============================================================
# VALIDATION
# ============================================================

if not API_KEY:
    raise RuntimeError("OKX_API_KEY is missing")

if not SECRET_KEY:
    raise RuntimeError("OKX_SECRET_KEY is missing")

if not PASSPHRASE:
    raise RuntimeError("OKX_PASSPHRASE is missing")


# ============================================================
# OKX API
# ============================================================

api = Trade.TradeAPI(
    api_key=API_KEY,
    api_secret_key=SECRET_KEY,
    passphrase=PASSPHRASE,
    flag=FLAG,
)


# ============================================================
# HELPERS
# ============================================================

def D(value):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def utc_time_from_ms(ts):
    return datetime.fromtimestamp(
        int(ts) / 1000,
        timezone.utc,
    )


# ============================================================
# GET FILLS
# ============================================================

def get_all_recent_fills():

    all_fills = []
    seen = set()

    # First request.
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

            key = (
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

            if key not in seen:
                seen.add(key)
                all_fills.append(row)

        if len(rows) < LIMIT:
            break

        timestamps = [
            int(row["ts"])
            for row in rows
            if row.get("ts")
        ]

        if not timestamps:
            break

        oldest_ts = min(timestamps)

        # OKX pagination:
        # before = older timestamp
        response = api.get_fills_history(
            instType=INST_TYPE,
            instId=INST_ID,
            before=str(oldest_ts),
            limit=str(LIMIT),
        )

        if response.get("code") != "0":
            raise RuntimeError(
                "OKX API Error: " + str(response)
            )

        new_rows = response.get("data", [])

        if not new_rows:
            break

        if len(new_rows) == len(rows):

            new_keys = {
                (
                    x.get("tradeId")
                    or x.get("fillId")
                    or (
                        x.get("ordId"),
                        x.get("ts"),
                        x.get("side"),
                        x.get("fillPx"),
                        x.get("fillSz"),
                    )
                )
                for x in new_rows
            }

            old_keys = {
                (
                    x.get("tradeId")
                    or x.get("fillId")
                    or (
                        x.get("ordId"),
                        x.get("ts"),
                        x.get("side"),
                        x.get("fillPx"),
                        x.get("fillSz"),
                    )
                )
                for x in rows
            }

            if new_keys == old_keys:
                break

        rows = new_rows

    return all_fills


# ============================================================
# FILTER LAST 24 HOURS
# ============================================================

def filter_last_24h(fills):

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    result = []

    for row in fills:

        ts = row.get("ts")

        if not ts:
            continue

        ts_int = int(ts)

        if start_ms <= ts_int <= end_ms:
            result.append(row)

    result.sort(
        key=lambda x: int(x.get("ts", "0"))
    )

    return result, start, now


# ============================================================
# ANALYZE
# ============================================================

def analyze(fills):

    buys = []
    sells = []

    buy_btc = D("0")
    sell_btc = D("0")

    buy_value = D("0")
    sell_value = D("0")

    fees_btc = D("0")
    fees_usdt = D("0")

    for row in fills:

        side = row.get("side", "").lower()

        px = D(row.get("fillPx"))
        sz = D(row.get("fillSz"))

        value = px * sz

        fee = abs(
            D(row.get("fee"))
        )

        fee_ccy = row.get(
            "feeCcy",
            "",
        ).upper()

        if side == "buy":

            buys.append(row)

            buy_btc += sz
            buy_value += value

        elif side == "sell":

            sells.append(row)

            sell_btc += sz
            sell_value += value

        if fee_ccy == "BTC":
            fees_btc += fee

        elif fee_ccy == "USDT":
            fees_usdt += fee

    return {
        "buys": buys,
        "sells": sells,
        "buy_btc": buy_btc,
        "sell_btc": sell_btc,
        "buy_value": buy_value,
        "sell_value": sell_value,
        "fees_btc": fees_btc,
        "fees_usdt": fees_usdt,
    }


# ============================================================
# GRID CYCLE MATCHING
# ============================================================

def match_grid_cycles(fills):

    inventory = []
    cycles = []

    for row in fills:

        side = row.get(
            "side",
            "",
        ).lower()

        px = D(row.get("fillPx"))
        sz = D(row.get("fillSz"))

        fee = abs(
            D(row.get("fee"))
        )

        fee_ccy = row.get(
            "feeCcy",
            "",
        ).upper()

        ts = int(
            row.get(
                "ts",
                "0",
            )
        )

        if side == "buy":

            net_btc = sz

            if fee_ccy == "BTC":
                net_btc -= fee

            inventory.append({
                "ts": ts,
                "price": px,
                "qty": net_btc,
                "buy_fee_btc": fee if fee_ccy == "BTC" else D("0"),
                "ordId": row.get("ordId", ""),
                "tradeId": row.get("tradeId", ""),
            })

        elif side == "sell":

            remaining = sz

            if fee_ccy == "BTC":
                remaining -= fee

            # FIFO matching.
            while remaining > 0 and inventory:

                buy = inventory[0]

                matched = min(
                    remaining,
                    buy["qty"],
                )

                buy_cost = (
                    buy["price"]
                    * matched
                )

                sell_value = (
                    px
                    * matched
                )

                # USDT fee belongs to sell.
                sell_fee = D("0")

                if fee_ccy == "USDT":

                    total_sell_qty = sz

                    if total_sell_qty > 0:

                        sell_fee = (
                            fee
                            * matched
                            / total_sell_qty
                        )

                pnl = (
                    sell_value
                    - buy_cost
                    - sell_fee
                )

                cycles.append({
                    "buy_ts": buy["ts"],
                    "sell_ts": ts,
                    "buy_price": buy["price"],
                    "sell_price": px,
                    "qty": matched,
                    "gross_pnl": (
                        sell_value
                        - buy_cost
                    ),
                    "sell_fee_usdt": sell_fee,
                    "net_pnl": pnl,
                    "buy_ordId": buy["ordId"],
                    "sell_ordId": row.get(
                        "ordId",
                        "",
                    ),
                })

                buy["qty"] -= matched
                remaining -= matched

                if buy["qty"] <= 0:
                    inventory.pop(0)

    return cycles, inventory


# ============================================================
# CSV
# ============================================================

def save_fills_csv(fills):

    filename = (
        "okx_demo_fills_24h_v04.csv"
    )

    columns = [
        "datetime_utc",
        "tradeId",
        "ordId",
        "side",
        "fillPx",
        "fillSz",
        "fee",
        "feeCcy",
        "instId",
        "execType",
        "ts",
    ]

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.writer(f)

        writer.writerow(columns)

        for row in fills:

            ts = row.get(
                "ts",
                "",
            )

            dt = ""

            if ts:
                dt = utc_time_from_ms(ts).isoformat()

            writer.writerow([
                dt,
                row.get("tradeId", ""),
                row.get("ordId", ""),
                row.get("side", ""),
                row.get("fillPx", ""),
                row.get("fillSz", ""),
                row.get("fee", ""),
                row.get("feeCcy", ""),
                row.get("instId", ""),
                row.get("execType", ""),
                ts,
            ])

    return filename


def save_cycles_csv(cycles):

    filename = (
        "okx_demo_grid_cycles_v04.csv"
    )

    columns = [
        "buy_time_utc",
        "sell_time_utc",
        "buy_price",
        "sell_price",
        "qty_btc",
        "gross_pnl_usdt",
        "sell_fee_usdt",
        "net_pnl_usdt",
        "buy_ordId",
        "sell_ordId",
    ]

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.writer(f)

        writer.writerow(columns)

        for cycle in cycles:

            writer.writerow([
                utc_time_from_ms(
                    cycle["buy_ts"]
                ).isoformat(),

                utc_time_from_ms(
                    cycle["sell_ts"]
                ).isoformat(),

                cycle["buy_price"],
                cycle["sell_price"],
                cycle["qty"],
                cycle["gross_pnl"],
                cycle["sell_fee_usdt"],
                cycle["net_pnl"],
                cycle["buy_ordId"],
                cycle["sell_ordId"],
            ])

    return filename


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 76)
    print("        OKX DEMO v4 REALIZED P/L REPORT")
    print("             BTC-USDT / LAST 24H")
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

    print()
    print("Loading fills from OKX...")

    all_fills = get_all_recent_fills()

    fills, start, now = filter_last_24h(
        all_fills
    )

    result = analyze(fills)

    cycles, remaining = match_grid_cycles(
        fills
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
        "All fills fetched :",
        len(all_fills),
    )

    print(
        "24H fills         :",
        len(fills),
    )

    print()
    print("=" * 76)
    print("TRADING")
    print("=" * 76)

    print(
        "BUY fills         :",
        len(result["buys"]),
    )

    print(
        "SELL fills        :",
        len(result["sells"]),
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
        "BTC fees          :",
        f"{result['fees_btc']:.8f}",
        "BTC",
    )

    print(
        "USDT fees         :",
        f"{result['fees_usdt']:.8f}",
        "USDT",
    )

    print()
    print("=" * 76)
    print("REALIZED GRID P/L")
    print("=" * 76)

    winning = [
        x
        for x in cycles
        if x["net_pnl"] > 0
    ]

    losing = [
        x
        for x in cycles
        if x["net_pnl"] < 0
    ]

    realized_pnl = sum(
        (
            x["net_pnl"]
            for x in cycles
        ),
        D("0"),
    )

    gross_profit = sum(
        (
            x["net_pnl"]
            for x in winning
        ),
        D("0"),
    )

    gross_loss = abs(
        sum(
            (
                x["net_pnl"]
                for x in losing
            ),
            D("0"),
        )
    )

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else Decimal("Infinity")
    )

    win_rate = (
        Decimal(len(winning))
        / Decimal(len(cycles))
        * Decimal("100")
        if cycles
        else D("0")
    )

    print(
        "Completed cycles  :",
        len(cycles),
    )

    print(
        "Winning cycles    :",
        len(winning),
    )

    print(
        "Losing cycles     :",
        len(losing),
    )

    print(
        "Win rate          :",
        f"{win_rate:.2f}%",
    )

    print(
        "Realized P/L      :",
        f"{realized_pnl:.6f}",
        "USDT",
    )

    print(
        "Profit factor     :",
        (
            "INF"
            if profit_factor.is_infinite()
            else f"{profit_factor:.4f}"
        ),
    )

    print()
    print("=" * 76)
    print("OPEN INVENTORY FROM MATCHING")
    print("=" * 76)

    remaining_qty = sum(
        (
            x["qty"]
            for x in remaining
        ),
        D("0"),
    )

    print(
        "Unmatched BUY BTC :",
        f"{remaining_qty:.8f}",
    )

    print()
    print("=" * 76)
    print("SAVING")
    print("=" * 76)

    fill_csv = save_fills_csv(
        fills
    )

    cycle_csv = save_cycles_csv(
        cycles
    )

    print(
        "Fills CSV          :",
        fill_csv,
    )

    print(
        "Grid cycles CSV    :",
        cycle_csv,
    )

    print()
    print("=" * 76)
    print("OKX DEMO v4 COMPLETE")
    print("=" * 76)
    print()
    print(
        "READ ONLY - NO ORDERS CREATED"
    )
    print(
        "READ ONLY - NO ORDERS CANCELLED"
    )


if __name__ == "__main__":
    main()