import sys
import os
import csv
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path

import okx.Trade as Trade
from dotenv import load_dotenv


# ============================================================
# OKX DEMO PERFORMANCE REPORT v0.7
# 5 BOT / 2 SYMBOL REPORTER
# READ ONLY - NO ORDERS CREATED / CANCELLED
# ============================================================

BOTS = [
    {
        "id": "A",
        "name": "A / v4.8",
        "symbol": "BTC-USDT",
        "env": ".env",
        "prefix": "v048",
        "folder": "reports_csv/BTC_A_v048",
    },
    {
        "id": "B",
        "name": "B / v4.9",
        "symbol": "BTC-USDT",
        "env": ".env.v49",
        "prefix": "v049",
        "folder": "reports_csv/BTC_B_v049",
    },
    {
        "id": "C",
        "name": "C / v5.1.1",
        "symbol": "BTC-USDT",
        "env": ".env.v50",
        "prefix": "V511",
        "folder": "reports_csv/BTC_C_v511",
    },
    {
        "id": "D",
        "name": "D / ETH v4.8",
        "symbol": "ETH-USDT",
        "env": ".env",
        "prefix": "ETHv048",
        "folder": "reports_csv/ETH_D_v048",
    },
    {
        "id": "E",
        "name": "E / ETH v4.9",
        "symbol": "ETH-USDT",
        "env": ".env.v49",
        "prefix": "ETHv049",
        "folder": "reports_csv/ETH_E_v049",
    },
]

D = Decimal


def now_utc():
    return datetime.now(timezone.utc)


def parse_ts(ts):
    return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)


def money(x):
    return D(str(x or "0"))


def fmt_dec(x, places=8):
    return f"{D(str(x)):.{places}f}"


def get_period(hours):
    end = now_utc()
    return end - timedelta(hours=hours), end


def load_account(bot):
    load_dotenv(bot["env"], override=True)

    api_key = os.getenv("OKX_API_KEY")
    secret_key = os.getenv("OKX_SECRET_KEY")
    passphrase = os.getenv("OKX_PASSPHRASE")
    flag = os.getenv("OKX_FLAG", "1")

    if not api_key or not secret_key or not passphrase:
        raise RuntimeError(f"{bot['name']}: missing OKX credentials in {bot['env']}")

    if flag != "1":
        raise RuntimeError(f"{bot['name']}: safety stop - OKX_FLAG must be 1 (DEMO), got {flag}")

    api = Trade.TradeAPI(
        api_key=api_key,
        api_secret_key=secret_key,
        passphrase=passphrase,
        flag=flag,
        debug=False,
        domain="https://www.okx.com",
    )
    return api


def fetch_fills(api, symbol):
    all_fills = []
    after = None

    while True:
        kwargs = {"instType": "SPOT", "instId": symbol, "limit": "100"}
        if after:
            kwargs["after"] = after

        result = api.get_fills(**kwargs)
        if result.get("code") != "0":
            raise RuntimeError(f"OKX get_fills error: {result}")

        rows = result.get("data", [])
        if not rows:
            break

        all_fills.extend(rows)
        if len(rows) < 100 or len(all_fills) >= 1000:
            break

        last = rows[-1].get("billId")
        if not last or last == after:
            break
        after = last

    return all_fills


def filter_period(fills, start, end):
    rows = []
    for fill in fills:
        ts = fill.get("ts")
        if not ts:
            continue
        t = parse_ts(ts)
        if start <= t <= end:
            rows.append(fill)
    rows.sort(key=lambda x: int(x.get("ts", 0)))
    return rows


def build_cycles(fills):
    cycles = []
    inventory = []
    cycle_id = 0

    for fill in fills:
        side = fill.get("side", "").lower()
        px = money(fill.get("fillPx"))
        sz = money(fill.get("fillSz"))
        if px <= 0 or sz <= 0:
            continue

        fee = money(fill.get("fee"))
        item = {
            "ts": fill.get("ts"),
            "side": side,
            "price": px,
            "size": sz,
            "fee": fee,
        }

        if side == "buy":
            inventory.append(item)
            continue

        if side != "sell":
            continue

        remaining = sz
        while remaining > 0 and inventory:
            buy = inventory[0]
            match_size = min(remaining, buy["size"])

            buy_value = buy["price"] * match_size
            sell_value = px * match_size
            buy_fee = abs(buy["fee"]) * match_size / buy["size"] if buy["size"] > 0 else D("0")
            sell_fee = abs(fee) * match_size / sz if sz > 0 else D("0")
            pnl = sell_value - buy_value - buy_fee - sell_fee

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


def make_report(bot, fills, start, end):
    buys = [f for f in fills if f.get("side", "").lower() == "buy"]
    sells = [f for f in fills if f.get("side", "").lower() == "sell"]

    bought = sum((money(f.get("fillSz")) for f in buys), D("0"))
    sold = sum((money(f.get("fillSz")) for f in sells), D("0"))
    buy_value = sum((money(f.get("fillPx")) * money(f.get("fillSz")) for f in buys), D("0"))
    sell_value = sum((money(f.get("fillPx")) * money(f.get("fillSz")) for f in sells), D("0"))

    fee_by_ccy = {}
    for f in fills:
        fee = abs(money(f.get("fee")))
        ccy = f.get("feeCcy", "") or ""
        fee_by_ccy[ccy] = fee_by_ccy.get(ccy, D("0")) + fee

    cycles, inventory = build_cycles(fills)
    winning = [c for c in cycles if c["pnl"] > 0]
    losing = [c for c in cycles if c["pnl"] < 0]
    realized = sum((c["pnl"] for c in cycles), D("0"))
    gross_profit = sum((c["pnl"] for c in winning), D("0"))
    gross_loss = abs(sum((c["pnl"] for c in losing), D("0")))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    avg_cycle = realized / D(len(cycles)) if cycles else D("0")
    best = max((c["pnl"] for c in cycles), default=D("0"))
    worst = min((c["pnl"] for c in cycles), default=D("0"))
    win_rate = D(len(winning)) / D(len(cycles)) * D("100") if cycles else D("0")
    unmatched = sum((x["size"] for x in inventory), D("0"))

    return {
        "bot": bot,
        "fills": fills,
        "cycles": cycles,
        "start": start,
        "end": end,
        "buy_count": len(buys),
        "sell_count": len(sells),
        "bought": bought,
        "sold": sold,
        "buy_value": buy_value,
        "sell_value": sell_value,
        "fees": fee_by_ccy,
        "completed_cycles": len(cycles),
        "winning_cycles": len(winning),
        "losing_cycles": len(losing),
        "win_rate": win_rate,
        "realized": realized,
        "profit_factor": profit_factor,
        "avg_cycle": avg_cycle,
        "best_cycle": best,
        "worst_cycle": worst,
        "unmatched": unmatched,
    }


def save_csv(report, hours):
    bot = report["bot"]
    out_dir = Path(bot["folder"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["end"].strftime("%Y%m%d_%H%M%S")

    fills_name = out_dir / f"{bot['symbol'].replace('-', '')}_fills_{bot['prefix']}_{hours}h_{stamp}.csv"
    cycles_name = out_dir / f"{bot['symbol'].replace('-', '')}_cycles_{bot['prefix']}_{hours}h_{stamp}.csv"

    with fills_name.open("w", newline="", encoding="utf-8-sig") as fp:
        fields = sorted(set().union(*(f.keys() for f in report["fills"]))) if report["fills"] else ["ts", "side", "fillPx", "fillSz", "fee", "feeCcy"]
        writer = csv.DictWriter(fp, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["fills"])

    with cycles_name.open("w", newline="", encoding="utf-8-sig") as fp:
        fields = ["cycle", "buy_time", "sell_time", "buy_price", "sell_price", "size", "buy_value", "sell_value", "fees", "pnl"]
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for row in report["cycles"]:
            writer.writerow(row)

    return str(fills_name), str(cycles_name)


def print_report(report, hours):
    bot = report["bot"]
    print("\n" + "=" * 76)
    print("        OKX DEMO PERFORMANCE REPORT v0.7")
    print(f"             {bot['name']} | {bot['symbol']}")
    print("=" * 76)
    print(f"Mode       : DEMO")
    print(f"Symbol     : {bot['symbol']}")
    print(f"Period     : LAST {hours} HOURS")
    print(f"From       : {report['start']}")
    print(f"To         : {report['end']}")
    print(f"Fills              : {len(report['fills'])}")
    print(f"BUY fills          : {report['buy_count']}")
    print(f"SELL fills         : {report['sell_count']}")
    print(f"Bought {bot['symbol'][:3]} : {fmt_dec(report['bought'])}")
    print(f"Sold {bot['symbol'][:3]}   : {fmt_dec(report['sold'])}")
    print(f"BUY value          : {report['buy_value']:.6f} USDT")
    print(f"SELL value         : {report['sell_value']:.6f} USDT")
    print("-" * 76)
    print(f"Completed cycles   : {report['completed_cycles']}")
    print(f"Winning cycles     : {report['winning_cycles']}")
    print(f"Losing cycles      : {report['losing_cycles']}")
    print(f"Win rate           : {report['win_rate']:.2f}%")
    print(f"Realized P/L       : {report['realized']:.6f} USDT")
    pf = "INF" if report["profit_factor"] is None else f"{report['profit_factor']:.4f}"
    print(f"Profit factor      : {pf}")
    print(f"Avg cycle P/L      : {report['avg_cycle']:.6f} USDT")
    print(f"Best cycle         : {report['best_cycle']:.6f} USDT")
    print(f"Worst cycle        : {report['worst_cycle']:.6f} USDT")
    print(f"Unmatched BUY      : {fmt_dec(report['unmatched'])}")
    print("Fees by currency   : " + (", ".join(f"{k}={v:.8f}" for k, v in sorted(report['fees'].items())) or "NONE"))


def print_comparison(reports, hours):
    print("\n" + "=" * 110)
    print(f"                 5-BOT DEMO COMPARISON - LAST {hours} HOURS")
    print("=" * 110)
    print(f"{'Bot':<18}{'Symbol':<12}{'Fills':>8}{'Cycles':>9}{'Win%':>9}{'Realized':>14}{'PF':>10}{'Unmatched':>14}")
    print("-" * 110)
    for r in reports:
        pf = "INF" if r["profit_factor"] is None else f"{r['profit_factor']:.4f}"
        print(f"{r['bot']['name']:<18}{r['bot']['symbol']:<12}{len(r['fills']):>8}{r['completed_cycles']:>9}{r['win_rate']:>8.2f}%{r['realized']:>14.6f}{pf:>10}{r['unmatched']:>14.8f}")
    print("-" * 110)
    print("NOTE: BTC bots are compared directly with each other; ETH is shown separately because symbol/price scale differs.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python okx_demo_report_abc.py <hours>")
        print("Example: python okx_demo_report_abc.py 12")
        sys.exit(1)

    hours = int(sys.argv[1])
    if hours <= 0:
        raise ValueError("hours must be greater than 0")

    start, end = get_period(hours)
    reports = []

    for bot in BOTS:
        print(f"\nLoading fills from {bot['name']} / {bot['symbol']}...")
        api = load_account(bot)
        all_fills = fetch_fills(api, bot["symbol"])
        period_fills = filter_period(all_fills, start, end)
        report = make_report(bot, period_fills, start, end)
        reports.append(report)
        print_report(report, hours)
        fills_file, cycles_file = save_csv(report, hours)
        print("-" * 76)
        print(f"CSV folder         : {bot['folder']}")
        print(f"Fills CSV          : {fills_file}")
        print(f"Cycles CSV         : {cycles_file}")

    print_comparison(reports, hours)
    print("\n" + "=" * 76)
    print("REPORT COMPLETE")
    print("READ ONLY - NO ORDERS CREATED")
    print("READ ONLY - NO ORDERS CANCELLED")
    print("=" * 76)


if __name__ == "__main__":
    main()
