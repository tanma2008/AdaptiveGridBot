import sys
import os
import csv
from decimal import Decimal
from datetime import datetime, timedelta, timezone

import okx.Trade as Trade
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

SYMBOL = "BTC-USDT"

ACCOUNT_A = {
    "name": "A / v4.8",
    "env": ".env",
    "prefix": "v048",
}

ACCOUNT_B = {
    "name": "B / v4.9",
    "env": ".env.v49",
    "prefix": "v049",
}

ACCOUNT_C = {
    "name": "C / v5.1.1",
    "env": ".env.v50",
    "prefix": "V511",
}


# ============================================================
# HELPERS
# ============================================================

D = Decimal


def now_utc():
    return datetime.now(timezone.utc)


def parse_ts(ts):
    return datetime.fromtimestamp(
        int(ts) / 1000,
        tz=timezone.utc
    )


def money(x):
    return D(str(x))


def fmt_dec(x, places=8):
    return f"{D(str(x)):.{places}f}"


def get_period(hours):
    end = now_utc()
    start = end - timedelta(hours=hours)
    return start, end


def load_account(account):
    load_dotenv(account["env"], override=True)

    api_key = os.getenv("OKX_API_KEY")
    secret_key = os.getenv("OKX_SECRET_KEY")
    passphrase = os.getenv("OKX_PASSPHRASE")
    flag = os.getenv("OKX_FLAG", "1")

    if not api_key:
        raise RuntimeError(
            f"{account['name']}: OKX_API_KEY missing "
            f"in {account['env']}"
        )

    if not secret_key:
        raise RuntimeError(
            f"{account['name']}: OKX_SECRET_KEY missing "
            f"in {account['env']}"
        )

    if not passphrase:
        raise RuntimeError(
            f"{account['name']}: OKX_PASSPHRASE missing "
            f"in {account['env']}"
        )

    api = Trade.TradeAPI(
        api_key=api_key,
        api_secret_key=secret_key,
        passphrase=passphrase,
        flag=flag,
        debug=False,
        domain="https://www.okx.com",
    )

    return api


# ============================================================
# FETCH FILLS
# ============================================================

def fetch_fills(api):
    all_fills = []

    after = None

    while True:

        kwargs = {
            "instType": "SPOT",
            "instId": SYMBOL,
            "limit": "100",
        }

        if after:
            kwargs["after"] = after

        result = api.get_fills(**kwargs)

        if result.get("code") != "0":
            raise RuntimeError(
                f"OKX get_fills error: {result}"
            )

        rows = result.get("data", [])

        if not rows:
            break

        all_fills.extend(rows)

        if len(rows) < 100:
            break

        last = rows[-1].get("billId")

        if not last:
            break

        if last == after:
            break

        after = last

        if len(all_fills) >= 1000:
            break

    return all_fills


# ============================================================
# FILTER PERIOD
# ============================================================

def filter_period(fills, start, end):

    result = []

    for f in fills:

        ts = f.get("ts")

        if not ts:
            continue

        t = parse_ts(ts)

        if start <= t <= end:
            result.append(f)

    result.sort(
        key=lambda x: int(x.get("ts", 0))
    )

    return result


# ============================================================
# BUILD CYCLES
# ============================================================

def build_cycles(fills):

    cycles = []

    inventory = []

    cycle_id = 0

    for fill in fills:

        side = fill.get("side", "").lower()

        px = money(fill.get("fillPx", "0"))
        sz = money(fill.get("fillSz", "0"))

        if px <= 0 or sz <= 0:
            continue

        fee = money(fill.get("fee", "0"))

        value = px * sz

        item = {
            "ts": fill.get("ts"),
            "side": side,
            "price": px,
            "size": sz,
            "value": value,
            "fee": fee,
            "fill": fill,
        }

        if side == "buy":

            inventory.append(item)

        elif side == "sell":

            remaining = sz

            while remaining > 0 and inventory:

                buy = inventory[0]

                match_size = min(
                    remaining,
                    buy["size"]
                )

                buy_value = (
                    buy["price"] * match_size
                )

                sell_value = (
                    px * match_size
                )

                # Approximate fee allocation
                buy_fee = (
                    abs(buy["fee"])
                    * match_size
                    / buy["size"]
                    if buy["size"] > 0
                    else D("0")
                )

                sell_fee = (
                    abs(fee)
                    * match_size
                    / sz
                    if sz > 0
                    else D("0")
                )

                pnl = (
                    sell_value
                    - buy_value
                    - buy_fee
                    - sell_fee
                )

                cycle_id += 1

                cycles.append({
                    "cycle": cycle_id,
                    "buy_time": buy["ts"],
                    "sell_time": item["ts"],
                    "buy_price": buy["price"],
                    "sell_price": px,
                    "size": match_size,
                    "buy_value": buy_value,
                    "sell_value": sell_value,
                    "fees": buy_fee + sell_fee,
                    "pnl": pnl,
                })

                buy["size"] -= match_size
                remaining -= match_size

                if buy["size"] <= D("0"):
                    inventory.pop(0)

    return cycles, inventory


# ============================================================
# REPORT
# ============================================================

def make_report(account, fills, start, end):

    buys = [
        f for f in fills
        if f.get("side", "").lower() == "buy"
    ]

    sells = [
        f for f in fills
        if f.get("side", "").lower() == "sell"
    ]

    bought_btc = sum(
        (money(f.get("fillSz", "0")) for f in buys),
        D("0")
    )

    sold_btc = sum(
        (money(f.get("fillSz", "0")) for f in sells),
        D("0")
    )

    buy_value = sum(
        (
            money(f.get("fillPx", "0"))
            * money(f.get("fillSz", "0"))
            for f in buys
        ),
        D("0")
    )

    sell_value = sum(
        (
            money(f.get("fillPx", "0"))
            * money(f.get("fillSz", "0"))
            for f in sells
        ),
        D("0")
    )

    btc_fee = D("0")
    usdt_fee = D("0")

    for f in fills:

        fee = abs(money(f.get("fee", "0")))
        fee_ccy = f.get("feeCcy", "")

        if fee_ccy == "BTC":
            btc_fee += fee

        elif fee_ccy == "USDT":
            usdt_fee += fee

    cycles, inventory = build_cycles(fills)

    winning = [
        c for c in cycles
        if c["pnl"] > 0
    ]

    losing = [
        c for c in cycles
        if c["pnl"] < 0
    ]

    realized = sum(
        (c["pnl"] for c in cycles),
        D("0")
    )

    gross_profit = sum(
        (c["pnl"] for c in winning),
        D("0")
    )

    gross_loss = abs(sum(
        (c["pnl"] for c in losing),
        D("0")
    ))

    if gross_loss > 0:
        profit_factor = (
            gross_profit / gross_loss
        )
    else:
        profit_factor = None

    if cycles:
        avg_cycle = (
            realized / D(len(cycles))
        )
        best_cycle = max(
            c["pnl"] for c in cycles
        )
        worst_cycle = min(
            c["pnl"] for c in cycles
        )
    else:
        avg_cycle = D("0")
        best_cycle = D("0")
        worst_cycle = D("0")

    win_rate = (
        D(len(winning))
        / D(len(cycles))
        * D("100")
        if cycles
        else D("0")
    )

    unmatched_buy = sum(
        (x["size"] for x in inventory),
        D("0")
    )

    return {
        "account": account,
        "fills": fills,
        "cycles": cycles,
        "start": start,
        "end": end,
        "buy_count": len(buys),
        "sell_count": len(sells),
        "bought_btc": bought_btc,
        "sold_btc": sold_btc,
        "buy_value": buy_value,
        "sell_value": sell_value,
        "btc_fee": btc_fee,
        "usdt_fee": usdt_fee,
        "completed_cycles": len(cycles),
        "winning_cycles": len(winning),
        "losing_cycles": len(losing),
        "win_rate": win_rate,
        "realized": realized,
        "profit_factor": profit_factor,
        "avg_cycle": avg_cycle,
        "best_cycle": best_cycle,
        "worst_cycle": worst_cycle,
        "unmatched_buy": unmatched_buy,
    }


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(report, hours):

    account = report["account"]

    prefix = account["prefix"]

    timestamp = (
        report["end"]
        .strftime("%Y%m%d_%H%M%S")
    )

    fills_name = (
        f"okx_demo_fills_{prefix}_{hours}h_"
        f"{timestamp}.csv"
    )

    cycles_name = (
        f"okx_demo_cycles_{prefix}_{hours}h_"
        f"{timestamp}.csv"
    )

    with open(
        fills_name,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as fp:

        if report["fills"]:

            fields = sorted(
                set().union(
                    *[
                        f.keys()
                        for f in report["fills"]
                    ]
                )
            )

            writer = csv.DictWriter(
                fp,
                fieldnames=fields,
                extrasaction="ignore"
            )

            writer.writeheader()

            for row in report["fills"]:
                writer.writerow(row)

    with open(
        cycles_name,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as fp:

        fields = [
            "cycle",
            "buy_time",
            "sell_time",
            "buy_price",
            "sell_price",
            "size",
            "buy_value",
            "sell_value",
            "fees",
            "pnl",
        ]

        writer = csv.DictWriter(
            fp,
            fieldnames=fields
        )

        writer.writeheader()

        for row in report["cycles"]:

            writer.writerow({
                "cycle": row["cycle"],
                "buy_time": row["buy_time"],
                "sell_time": row["sell_time"],
                "buy_price": row["buy_price"],
                "sell_price": row["sell_price"],
                "size": row["size"],
                "buy_value": row["buy_value"],
                "sell_value": row["sell_value"],
                "fees": row["fees"],
                "pnl": row["pnl"],
            })

    return fills_name, cycles_name


# ============================================================
# PRINT REPORT
# ============================================================

def print_report(report, hours):

    account = report["account"]

    print()
    print("=" * 76)
    print(
        f"        OKX DEMO PERFORMANCE REPORT v0.6"
    )
    print(
        f"             {account['name']}"
    )
    print("=" * 76)

    print()
    print(f"Mode       : DEMO")
    print(f"Symbol     : {SYMBOL}")
    print(f"Period     : LAST {hours} HOURS")

    print()
    print("=" * 76)
    print("PERIOD")
    print("=" * 76)

    print(
        f"From       : {report['start']}"
    )

    print(
        f"To         : {report['end']}"
    )

    print(
        f"Fills fetched     : {len(report['fills'])}"
    )

    print(
        f"Fills in period   : {len(report['fills'])}"
    )

    print()
    print("=" * 76)
    print("TRADING ACTIVITY")
    print("=" * 76)

    print(
        f"BUY fills         : {report['buy_count']}"
    )

    print(
        f"SELL fills        : {report['sell_count']}"
    )

    print(
        f"Bought BTC        : "
        f"{fmt_dec(report['bought_btc'])}"
    )

    print(
        f"Sold BTC          : "
        f"{fmt_dec(report['sold_btc'])}"
    )

    print(
        f"BUY value         : "
        f"{report['buy_value']:.6f} USDT"
    )

    print(
        f"SELL value        : "
        f"{report['sell_value']:.6f} USDT"
    )

    print()
    print("=" * 76)
    print("FEES")
    print("=" * 76)

    print(
        f"BTC fee           : "
        f"{fmt_dec(report['btc_fee'])}"
    )

    print(
        f"USDT fee          : "
        f"{report['usdt_fee']:.8f} USDT"
    )

    print()
    print("=" * 76)
    print("GRID PERFORMANCE")
    print("=" * 76)

    print(
        f"Completed cycles  : "
        f"{report['completed_cycles']}"
    )

    print(
        f"Winning cycles    : "
        f"{report['winning_cycles']}"
    )

    print(
        f"Losing cycles     : "
        f"{report['losing_cycles']}"
    )

    print(
        f"Win rate          : "
        f"{report['win_rate']:.2f}%"
    )

    print(
        f"Realized P/L      : "
        f"{report['realized']:.6f} USDT"
    )

    if report["profit_factor"] is None:
        pf = "INF"
    else:
        pf = f"{report['profit_factor']:.4f}"

    print(
        f"Profit factor     : {pf}"
    )

    print(
        f"Avg cycle P/L     : "
        f"{report['avg_cycle']:.6f} USDT"
    )

    print(
        f"Best cycle        : "
        f"{report['best_cycle']:.6f} USDT"
    )

    print(
        f"Worst cycle       : "
        f"{report['worst_cycle']:.6f} USDT"
    )

    print()
    print("=" * 76)
    print("OPEN INVENTORY")
    print("=" * 76)

    print(
        f"Unmatched BUY BTC : "
        f"{fmt_dec(report['unmatched_buy'])}"
    )


# ============================================================
# A/B SUMMARY
# ============================================================

def print_comparison(a, b, c, hours):

    print()
    print("=" * 90)
    print(
        f"             A / B / C COMPARISON - LAST {hours} HOURS"
    )
    print("=" * 90)

    print()

    print(
        f"{'Metric':<24}"
        f"{'v4.8 A':>18}"
        f"{'v4.9 B':>18}"
        f"{'v5.1.1 C':>18}"
    )

    print("-" * 78)

    def pf_value(r):
        return (
            "INF"
            if r["profit_factor"] is None
            else f"{r['profit_factor']:.4f}"
        )

    rows = [
        ("Fills", len(a["fills"]), len(b["fills"]), len(c["fills"])),
        ("Completed cycles", a["completed_cycles"], b["completed_cycles"], c["completed_cycles"]),
        ("Win rate %", f"{a['win_rate']:.2f}", f"{b['win_rate']:.2f}", f"{c['win_rate']:.2f}"),
        ("Realized P/L", f"{a['realized']:.6f}", f"{b['realized']:.6f}", f"{c['realized']:.6f}"),
        ("Profit factor", pf_value(a), pf_value(b), pf_value(c)),
        ("Avg cycle P/L", f"{a['avg_cycle']:.6f}", f"{b['avg_cycle']:.6f}", f"{c['avg_cycle']:.6f}"),
        ("Best cycle", f"{a['best_cycle']:.6f}", f"{b['best_cycle']:.6f}", f"{c['best_cycle']:.6f}"),
        ("Worst cycle", f"{a['worst_cycle']:.6f}", f"{b['worst_cycle']:.6f}", f"{c['worst_cycle']:.6f}"),
        ("Unmatched BUY BTC", f"{a['unmatched_buy']:.8f}", f"{b['unmatched_buy']:.8f}", f"{c['unmatched_buy']:.8f}"),
    ]

    for name, va, vb, vc in rows:
        print(
            f"{name:<24}"
            f"{str(va):>18}"
            f"{str(vb):>18}"
            f"{str(vc):>18}"
        )

    print()
    print(
        f"P/L difference B-A : {b['realized'] - a['realized']:+.6f} USDT"
    )
    print(
        f"P/L difference C-A : {c['realized'] - a['realized']:+.6f} USDT"
    )
    print(
        f"P/L difference C-B : {c['realized'] - b['realized']:+.6f} USDT"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) < 2:

        print(
            "Usage: python okx_demo_report_ab.py <hours>"
        )

        print(
            "Example: python okx_demo_report_ab.py 12"
        )

        sys.exit(1)

    hours = int(sys.argv[1])

    if hours <= 0:

        raise ValueError(
            "hours must be greater than 0"
        )

    start, end = get_period(hours)

    reports = []

    for account in [ACCOUNT_A, ACCOUNT_B, ACCOUNT_C]:

        print()
        print(
            f"Loading fills from "
            f"{account['name']}..."
        )

        api = load_account(account)

        all_fills = fetch_fills(api)

        period_fills = filter_period(
            all_fills,
            start,
            end
        )

        report = make_report(
            account,
            period_fills,
            start,
            end
        )

        reports.append(report)

        print_report(
            report,
            hours
        )

        fills_file, cycles_file = save_csv(
            report,
            hours
        )

        print()
        print("=" * 76)
        print("SAVING")
        print("=" * 76)

        print(
            f"Fills CSV         : {fills_file}"
        )

        print(
            f"Cycles CSV        : {cycles_file}"
        )

    print_comparison(
        reports[0],
        reports[1],
        reports[2],
        hours
    )

    print()
    print("=" * 76)
    print("REPORT COMPLETE")
    print("=" * 76)

    print()
    print("READ ONLY - NO ORDERS CREATED")
    print("READ ONLY - NO ORDERS CANCELLED")


if __name__ == "__main__":
    main()