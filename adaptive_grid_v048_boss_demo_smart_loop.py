import argparse
import json
import os
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from okx import Account, MarketData, Trade

from market_data import get_candles, candles_to_dataframe

RUN_ID = str(int(time.time()))[-6:]


# ============================================================================
# ADAPTIVE GRID BOT v4.8 BOSS
# BTC + ETH + SOL / ONE FILE / OKX DEMO
#
# Purpose:
#   Normalize the three v4.8 bots into one common runner without modifying
#   the original A / D / G files.
#
# Safety:
#   - DEMO only (FLAG=1)
#   - read-only by default
#   - --execute-demo is required to submit orders
#   - no cancel-all
#   - per-symbol inventory protection
#   - per-symbol exposure cap
#   - instrument tick/lot/min-size validation
# ============================================================================

load_dotenv(Path(__file__).with_name(".env"))

FLAG = "1"
STRATEGY_CAPITAL_USDT = Decimal("1000.00")
MAX_EXPOSURE_USDT = Decimal("500.00")
ORDER_SIZE_USDT = Decimal("10.00")
BUY_LEVELS = 10
SELL_LEVELS = 10
ATR_PERIOD = 30

LOW_THRESHOLD = Decimal("0.01")
NORMAL_THRESHOLD = Decimal("0.02")
HIGH_THRESHOLD = Decimal("0.03")
GRID_LOW = Decimal("0.0005")
GRID_NORMAL = Decimal("0.0010")
GRID_HIGH = Decimal("0.0020")
GRID_EXTREME = Decimal("0.0030")

BOTS = [
    {
        "id": "A",
        "name": "A / v4.8",
        "symbol": "BTC-USDT",
        "asset": "BTC",
        "prefix": "BOSS48A",
        "tick_fallback": Decimal("0.1"),
        "state": "adaptive_grid_v048_boss_BTC_state.json",
    },
    {
        "id": "D",
        "name": "D / ETH v4.8",
        "symbol": "ETH-USDT",
        "asset": "ETH",
        "prefix": "BOSS48D",
        "tick_fallback": Decimal("0.01"),
        "state": "adaptive_grid_v048_boss_ETH_state.json",
    },
    {
        "id": "G",
        "name": "G / SOL v4.8",
        "symbol": "SOL-USDT",
        "asset": "SOL",
        "prefix": "BOSS48G",
        "tick_fallback": Decimal("0.01"),
        "state": "adaptive_grid_v048_boss_SOL_state.json",
    },
]


def D(value):
    return Decimal(str(value))


def qdown(value, step):
    return (D(value) / D(step)).to_integral_value(rounding=ROUND_DOWN) * D(step)


def qup(value, step):
    """Round a quantity upward to the exchange lot size."""
    return (D(value) / D(step)).to_integral_value(rounding=ROUND_UP) * D(step)


def api_init():
    key = os.getenv("OKX_API_KEY")
    secret = os.getenv("OKX_SECRET_KEY")
    passphrase = os.getenv("OKX_PASSPHRASE")
    if not key or not secret or not passphrase:
        raise RuntimeError("Missing OKX API credentials in .env")

    market = MarketData.MarketAPI(key, secret, passphrase, False, FLAG)
    account = Account.AccountAPI(key, secret, passphrase, False, FLAG)
    trade = Trade.TradeAPI(key, secret, passphrase, False, FLAG)
    return market, account, trade


def account_balances(account):
    response = account.get_account_balance()
    if response.get("code") != "0":
        raise RuntimeError(f"OKX account error: {response}")

    wanted = {"USDT", "BTC", "ETH", "SOL"}
    balances = {ccy: Decimal("0") for ccy in wanted}
    details = response.get("data", [{}])[0].get("details", [])
    for item in details:
        ccy = item.get("ccy")
        if ccy in balances:
            balances[ccy] = D(item.get("availBal") or item.get("cashBal") or "0")
    return balances


def instrument_info(account, symbol):
    response = account.get_instruments(instType="SPOT")
    if response.get("code") != "0":
        raise RuntimeError(f"Instrument lookup failed: {response}")
    info = next((x for x in response.get("data", []) if x.get("instId") == symbol), None)
    if not info:
        raise RuntimeError(f"{symbol} instrument not found")
    if info.get("state") != "live":
        raise RuntimeError(f"{symbol} state is {info.get('state')}")

    return {
        "tick": D(info["tickSz"]),
        "lot": D(info["lotSz"]),
        "min_sz": D(info["minSz"]),
    }


def ticker_price(market, symbol):
    response = market.get_ticker(instId=symbol)
    if response.get("code") != "0":
        raise RuntimeError(f"Ticker failed for {symbol}: {response}")
    return D(response["data"][0]["last"])


def market_state(symbol):
    candles = get_candles(inst_id=symbol, bar="1D", limit="100")
    df = candles_to_dataframe(candles)
    if len(df) < ATR_PERIOD + 1:
        raise RuntimeError(f"{symbol}: not enough candles: {len(df)}")

    previous_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - previous_close).abs()
    tr3 = (df["low"] - previous_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean()

    price = D(df.iloc[-1]["close"])
    atr_value = D(atr.iloc[-1])
    atr_percent = atr_value / price
    regime, grid_percent = determine_regime(atr_percent)
    return price, atr_value, atr_percent, regime, grid_percent


def determine_regime(atr_percent):
    if atr_percent < LOW_THRESHOLD:
        return "LOW", GRID_LOW
    if atr_percent < NORMAL_THRESHOLD:
        return "NORMAL", GRID_NORMAL
    if atr_percent < HIGH_THRESHOLD:
        return "HIGH", GRID_HIGH
    return "EXTREME", GRID_EXTREME


def build_grid(price, grid_percent, tick):
    grid = []
    for level in range(1, BUY_LEVELS + 1):
        raw = price * (Decimal("1") - grid_percent * level)
        grid.append({
            "level": -level,
            "side": "buy",
            "price": qdown(raw, tick),
        })

    for level in range(1, SELL_LEVELS + 1):
        raw = price * (Decimal("1") + grid_percent * level)
        grid.append({
            "level": level,
            "side": "sell",
            "price": qdown(raw, tick),
        })
    return grid


def order_matches_grid(order, target):
    return (
        str(order.get("side", "")).lower() == target["side"]
        and D(order.get("px", "0")) == target["price"]
    )


def get_open_orders(trade, symbol):
    response = trade.get_order_list(instId=symbol)
    if response.get("code") != "0":
        raise RuntimeError(f"Open orders failed for {symbol}: {response}")
    return response.get("data", [])


def bot_open_orders(open_orders, prefix):
    # v4.8 historical bots used different prefixes. Boss must isolate its
    # own orders rather than accidentally touching another strategy.
    prefixes = {prefix}
    if prefix == "v048":
        prefixes.add("V048")
    if prefix == "G048":
        prefixes.add("G048")

    def ours(order):
        clid = str(order.get("clOrdId", ""))
        return any(clid.startswith(p) for p in prefixes)

    return [o for o in open_orders if ours(o)]


def normalize_qty(usdt_size, price, lot, min_sz):
    qty = qdown(D(usdt_size) / D(price), lot)
    if qty < min_sz:
        return None
    return qty


def load_state(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_state(path, state):
    Path(path).write_text(json.dumps(state, indent=2), encoding="utf-8")


def build_plan(bot, market, account, trade, balances, execute=False):
    symbol = bot["symbol"]
    asset = bot["asset"]
    info = instrument_info(account, symbol)
    price, atr, atr_percent, regime, grid_percent = market_state(symbol)
    live_price = ticker_price(market, symbol)
    open_all = get_open_orders(trade, symbol)
    ours = bot_open_orders(open_all, bot["prefix"])

    exposure = sum(
        (D(o.get("px", "0")) * D(o.get("sz", "0")) for o in ours),
        Decimal("0"),
    )

    grid = build_grid(live_price, grid_percent, info["tick"])
    missing = [g for g in grid if not any(order_matches_grid(o, g) for o in ours)]

    buy_missing = [g for g in missing if g["side"] == "buy"]
    sell_missing = [g for g in missing if g["side"] == "sell"]

    valid_buys = []
    for g in buy_missing:
        qty = normalize_qty(ORDER_SIZE_USDT, g["price"], info["lot"], info["min_sz"])
        if qty is not None and g["price"] * qty < ORDER_SIZE_USDT:
            qty = qup(ORDER_SIZE_USDT / g["price"], info["lot"])
            if qty < info["min_sz"]:
                qty = info["min_sz"]
        if qty is not None and g["price"] * qty >= ORDER_SIZE_USDT:
            valid_buys.append((g, qty))

    valid_sells = []
    reserved = Decimal("0")
    available_asset = balances.get(asset, Decimal("0"))
    for g in sell_missing:
        qty = normalize_qty(ORDER_SIZE_USDT, g["price"], info["lot"], info["min_sz"])
        if qty is None:
            continue
        if available_asset - reserved >= qty:
            reserved += qty
            valid_sells.append((g, qty))

    remaining = max(Decimal("0"), MAX_EXPOSURE_USDT - exposure)
    capacity = int(remaining / ORDER_SIZE_USDT)
    candidates = (valid_buys + valid_sells)[:capacity]

    open_buy = sum(1 for o in ours if o.get("side") == "buy")
    open_sell = sum(1 for o in ours if o.get("side") == "sell")

    print("-" * 76)
    print(f"{bot['name']} | {symbol}")
    print(f"Price            : ${live_price:,.6f}")
    print(f"ATR30D           : ${atr:,.6f}")
    print(f"ATR / Price      : {atr_percent * 100:.4f}%")
    print(f"Regime           : {regime}")
    print(f"Grid distance    : {grid_percent * 100:.4f}%")
    print(f"Open bot orders  : {len(ours)} ({open_buy} BUY / {open_sell} SELL)")
    print(f"Exposure         : ${exposure:,.2f} / ${MAX_EXPOSURE_USDT:,.2f}")
    print(f"Available {asset:4} : {available_asset}")
    print(f"Missing BUY      : {len(buy_missing)}")
    print(f"Missing SELL     : {len(sell_missing)}")
    print(f"Validated plan   : {len(candidates)} orders")

    if sell_missing and not valid_sells:
        print("SELL protection  : BLOCKED (insufficient inventory or size)")

    for g, qty in candidates:
        mode = "WOULD PLACE" if not execute else "PLACE"
        print(
            f"[{mode}] L{g['level']:+d} {g['side'].upper():4} "
            f"px=${g['price']:,.6f} qty={qty}"
        )

    placed_count = 0
    failed_count = 0
    if execute:
        for g, qty in candidates:
            base_clid = f"BOSS48{bot['id']}{'B' if g['side'] == 'buy' else 'S'}{abs(g['level']):02d}"
            clid = f"{base_clid}{RUN_ID}"
            params = {
                "instId": symbol,
                "tdMode": "cash",
                "clOrdId": clid,
                "side": g["side"],
                "ordType": "limit",
                "px": str(g["price"]),
                "sz": str(qty),
            }
            try:
                response = trade._request_with_params("POST", "/api/v5/trade/order", params)
                print(f"  -> {clid}: {response}")
                if response.get("code") == "0":
                    placed_count += 1
                else:
                    failed_count += 1
            except Exception as exc:
                failed_count += 1
                print(f"  -> {clid}: REQUEST FAILED - {type(exc).__name__}: {exc}")
                print("     [RECONCILE] Will verify open orders on the next cycle before placing again.")

        print(f"  EXECUTION RESULT : placed={placed_count} failed={failed_count}")

        # Re-read OKX after execution. The summary must describe the actual
        # post-execution open orders, not the pre-execution snapshot.
        post_all = get_open_orders(trade, symbol)
        ours = bot_open_orders(post_all, bot["prefix"])
        exposure = sum(
            (D(o.get("px", "0")) * D(o.get("sz", "0")) for o in ours),
            Decimal("0"),
        )
        open_buy = sum(1 for o in ours if o.get("side") == "buy")
        open_sell = sum(1 for o in ours if o.get("side") == "sell")
        print(
            f"  POST-EXECUTION   : open={len(ours)} "
            f"({open_buy} BUY / {open_sell} SELL) | exposure=${exposure:,.2f}"
        )

    save_state(bot["state"], {
        "symbol": symbol,
        "regime": regime,
        "grid_percent": str(grid_percent),
        "anchor": str(live_price),
        "orders_planned": len(candidates),
    })

    return {
        "id": bot["id"],
        "symbol": symbol,
        "orders": len(candidates),
        "open_orders": len(ours),
        "open_buy": open_buy,
        "open_sell": open_sell,
        "regime": regime,
        "exposure": exposure,
        "placed": placed_count,
        "failed": failed_count,
    }


def run_cycle(execute_demo=False):
    market, account, trade = api_init()
    balances = account_balances(account)

    print("=" * 76)
    print("       ADAPTIVE GRID BOT v4.8 BOSS")
    print("          BTC + ETH + SOL / OKX DEMO")
    print("=" * 76)
    print("Mode             : OKX DEMO ONLY")
    print(f"Order size       : ${ORDER_SIZE_USDT:.2f}")
    print(f"Grid             : {BUY_LEVELS} BUY / {SELL_LEVELS} SELL")
    print("Execution        : DEMO" if execute_demo else "Execution        : READ ONLY / DRY RUN")
    print("Safety           : no cancel-all; inventory protected")
    print()
    print("Balances:")
    for ccy in ("USDT", "BTC", "ETH", "SOL"):
        print(f"  {ccy:4} = {balances[ccy]}")

    results = []
    for bot in BOTS:
        results.append(build_plan(bot, market, account, trade, balances, execute_demo))

    # After execution, refresh from OKX so the report shows the actual
    # post-execution open orders, not the pre-cycle snapshot.
    if execute_demo:
        for r, bot in zip(results, BOTS):
            open_all = get_open_orders(trade, r["symbol"])
            ours = bot_open_orders(open_all, bot["prefix"])
            r["open_orders"] = len(ours)
            r["open_buy"] = sum(1 for o in ours if o.get("side") == "buy")
            r["open_sell"] = sum(1 for o in ours if o.get("side") == "sell")
            r["exposure"] = sum(
                (D(o.get("px", "0")) * D(o.get("sz", "0")) for o in ours),
                Decimal("0"),
            )

    print()
    print("=" * 76)
    print("v4.8 BOSS SUMMARY")
    print("=" * 76)
    for r in results:
        print(
            f"{r['id']} | {r['symbol']:8} | {r['regime']:7} | "
            f"open={r['open_orders']:2d} ({r['open_buy']:2d} BUY/{r['open_sell']:2d} SELL) | "
            f"planned={r['orders']:2d} | exposure=${r['exposure']:,.2f}"
        )

    print("-" * 76)
    print("OPEN ORDERS STATUS")
    for r in results:
        print(
            f"{r['symbol']:8} : {r['open_orders']:2d} orders "
            f"= {r['open_buy']:2d} BUY + {r['open_sell']:2d} SELL"
        )
    print(f"TOTAL    : {sum(r['open_orders'] for r in results):2d} orders")
    return results


def main():
    parser = argparse.ArgumentParser(description="Adaptive Grid v4.8 Boss - BTC/ETH/SOL")
    parser.add_argument("--execute-demo", action="store_true", help="submit validated orders to OKX DEMO")
    parser.add_argument("--once", action="store_true", help="run one reconciliation cycle")
    parser.add_argument("--loop", action="store_true", help="run reconciliation every 30 seconds")
    args = parser.parse_args()

    if FLAG != "1":
        raise RuntimeError("SAFETY STOP: Boss is DEMO only")
    if os.getenv("OKX_LIVE", "0") == "1":
        raise RuntimeError("LIVE GATE BLOCKED: OKX_LIVE=1 is not allowed")

    if args.loop:
        cycle = 0
        while True:
            cycle += 1
            print(f"\n{'=' * 76}")
            print(f"v4.8 BOSS SMART LOOP CYCLE {cycle}")
            print(f"{'=' * 76}")
            run_cycle(args.execute_demo)
            print("\nNext check in 30 seconds... Press Ctrl+C to stop.")
            time.sleep(30)
    else:
        run_cycle(args.execute_demo)


if __name__ == "__main__":
    main()
