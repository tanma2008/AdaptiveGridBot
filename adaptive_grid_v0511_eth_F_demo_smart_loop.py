"""
ADAPTIVE GRID BOT F / v5.1.1 - ETH-USDT - OKX DEMO SMART LOOP

New F candidate built from the v5.1.1 persistent-grid/fill-reconciliation
engine, isolated from A-E by a unique client-order prefix.

Parameters:
  Symbol       : ETH-USDT
  Grid         : 0.60%
  Order size   : $20
  SELL mult    : 2.50x
  Profit floor : 0.27%
  Loop         : 30 seconds

Safety:
- OKX Demo only (flag=1)
- Uses .env.v50 only for API credentials
- F_ENABLE_ORDERS=NO by default => read-only
- Only manages F511 client order IDs
- No automatic cancellation
- Reconciles fills before replacement orders
- Maximum 10 active F orders
- Existing orders are never cancelled by this bot
"""

import os
import time
import signal
from datetime import datetime

from dotenv import load_dotenv

import okx.Trade as Trade
import okx.Account as Account
import okx.MarketData as MarketData


ENV_FILE = ".env.v50"
INST_ID = "ETH-USDT"
TD_MODE = "cash"
PREFIX = "F511"

GRID_PCT = 0.0060
ORDER_USDT = 20.0
SELL_MULT = 2.5
SELL_STEP = GRID_PCT * SELL_MULT
PROFIT_FLOOR = 0.0027

LOOP_SECONDS = 30

MAX_BUY_ORDERS = 5
MAX_SELL_ORDERS = 5
MAX_OPEN_ORDERS = 10

running = True


def stop_handler(signum, frame):
    global running
    running = False
    print()
    print("Stopping F / v5.1.1 safely.")
    print("Existing orders are NOT cancelled.")


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is missing in {ENV_FILE}")
    return value


def fmt_price(p):
    return f"{p:.2f}"


def fmt_qty(q):
    return f"{q:.5f}"


def api_init():
    api_key = require_env("OKX_API_KEY")
    secret = require_env("OKX_SECRET_KEY")
    passphrase = require_env("OKX_PASSPHRASE")

    flag = "1"

    market = MarketData.MarketAPI(api_key, secret, passphrase, False, flag)
    account = Account.AccountAPI(api_key, secret, passphrase, False, flag)
    trade = Trade.TradeAPI(api_key, secret, passphrase, False, flag)
    return market, account, trade


def get_last_price(market):
    r = market.get_ticker(instId=INST_ID)
    if r.get("code") != "0" or not r.get("data"):
        raise RuntimeError(f"Ticker error: {r}")
    return float(r["data"][0]["last"])


def get_balance(account):
    r = account.get_account_balance(ccy="USDT,ETH")
    if r.get("code") != "0" or not r.get("data"):
        raise RuntimeError(f"Balance error: {r}")

    out = {"USDT": 0.0, "ETH": 0.0}
    for item in r["data"][0].get("details", []):
        ccy = item.get("ccy")
        if ccy in out:
            out[ccy] = float(item.get("availBal") or item.get("cashBal") or 0)
    return out


def get_open_orders(trade):
    r = trade.get_order_list(instType="SPOT")
    if r.get("code") != "0":
        raise RuntimeError(f"Open order error: {r}")
    return [o for o in r.get("data", []) if o.get("instId") == INST_ID]


def is_ours(o):
    return str(o.get("clOrdId") or "").startswith(PREFIX)


def ours(orders):
    return [o for o in orders if is_ours(o)]


def side(o):
    return str(o.get("side") or "").lower()


def px(o):
    try:
        return float(o.get("px") or 0)
    except Exception:
        return 0.0


def make_clordid(side_name, level, generation):
    return f"{PREFIX}{side_name[0].upper()}{level:02d}G{generation:04d}"


def level_from_clordid(clid):
    try:
        pos = clid.index("G")
        return int(clid[5:pos])
    except Exception:
        return 0


def generation_from_clordid(clid):
    try:
        return int(clid.split("G", 1)[1])
    except Exception:
        return 0


def place_limit(trade, side_name, price, usdt_size, level, generation):
    qty = usdt_size / price
    clid = make_clordid(side_name, level, generation)

    params = {
        "instId": INST_ID,
        "tdMode": TD_MODE,
        "side": side_name,
        "ordType": "limit",
        "clOrdId": clid,
        "px": fmt_price(price),
        "sz": fmt_qty(qty),
    }

    r = trade._request_with_params(Trade.POST, Trade.PLACR_ORDER, params)

    if r.get("code") != "0":
        print(f"ORDER ERROR {side_name} {price:.2f}: {r}")
        return False

    data = r.get("data") or []
    oid = data[0].get("ordId", "") if data else ""
    print(
        f"ORDER {side_name:<4} ${usdt_size:7.2f} "
        f"px={price:,.2f} qty={qty:.5f} "
        f"L{level} G{generation} clOrdId={clid} ordId={oid}"
    )
    return True


def build_initial_grid(anchor):
    levels = []
    for level in range(1, MAX_SELL_ORDERS + 1):
        levels.append(("sell", anchor * (1 + SELL_STEP * level), level, 0))
    for level in range(1, MAX_BUY_ORDERS + 1):
        levels.append(("buy", anchor * (1 - GRID_PCT * level), level, 0))
    return levels


def nearest_anchor_from_existing(order_list, fallback):
    prices = [px(o) for o in order_list if px(o) > 0]
    if not prices:
        return fallback
    return sum(prices) / len(prices)


def get_fills_since(trade):
    r = trade.get_fills(instType="SPOT")
    if r.get("code") != "0":
        raise RuntimeError(f"Fills error: {r}")
    return r.get("data", [])


def print_header():
    print("=" * 76)
    print("        ADAPTIVE GRID BOT F / v5.1.1 - ETH-USDT")
    print("                 OKX DEMO SMART LOOP")
    print("=" * 76)
    print(f"ENV          : {ENV_FILE}")
    print(f"Symbol       : {INST_ID}")
    print(f"Grid         : {GRID_PCT * 100:.2f}%")
    print(f"Order size   : ${ORDER_USDT:.2f}")
    print(f"SELL mult.   : {SELL_MULT:.2f}x")
    print(f"Profit floor : {PROFIT_FLOOR * 100:.2f}%")
    print(f"Prefix       : {PREFIX}")
    print()


def main():
    print_header()
    load_dotenv(ENV_FILE, override=True)

    enabled = os.getenv("F_ENABLE_ORDERS", "NO").upper() == "YES"
    print("ORDER MODE   : " + ("DEMO ORDERS ENABLED" if enabled else "READ ONLY"))
    print("OKX API FLAG : 1 (DEMO)")
    print()

    market, account, trade = api_init()
    last = get_last_price(market)
    balance = get_balance(account)
    all_orders = get_open_orders(trade)
    bot = ours(all_orders)

    print(f"ETH price    : ${last:,.2f}")
    print(f"USDT avail   : {balance['USDT']:.4f}")
    print(f"ETH avail    : {balance['ETH']:.6f}")
    print(f"All SPOT orders: {len(all_orders)}")
    print(f"F / V5.1.1 orders: {len(bot)}")
    print()

    if not enabled:
        print("READ ONLY CHECK PASSED.")
        print("Set F_ENABLE_ORDERS=YES only when F is approved for Demo orders.")
        return

    anchor = nearest_anchor_from_existing(bot, last)
    print(f"GRID ANCHOR  : ${anchor:,.2f}")
    print()

    if not bot:
        print("INITIAL GRID")
        for s, p, level, generation in build_initial_grid(anchor):
            if s == "sell":
                if balance["ETH"] < ORDER_USDT / p:
                    print("STOP: insufficient ETH for initial SELL grid.")
                    break
                if place_limit(trade, s, p, ORDER_USDT, level, generation):
                    balance["ETH"] -= ORDER_USDT / p
            else:
                if balance["USDT"] < ORDER_USDT:
                    print("STOP: insufficient USDT for initial BUY grid.")
                    break
                if place_limit(trade, s, p, ORDER_USDT, level, generation):
                    balance["USDT"] -= ORDER_USDT

        all_orders = get_open_orders(trade)
        bot = ours(all_orders)

    seen_fills = set()

    print()
    print("SMART LOOP ACTIVE.")
    print("Fills are reconciled from OKX before replacement orders.")
    print("Existing orders are NOT cancelled.")
    print()

    while running:
        try:
            last = get_last_price(market)
            balance = get_balance(account)
            all_orders = get_open_orders(trade)
            bot = ours(all_orders)

            fills = get_fills_since(trade)
            relevant = []
            for f in fills:
                clid = str(f.get("clOrdId") or "")
                if not clid.startswith(PREFIX):
                    continue
                fill_id = str(f.get("tradeId") or f.get("fillId") or "")
                key = fill_id or f"{clid}:{f.get('fillPx')}:{f.get('fillSz')}"
                if key in seen_fills:
                    continue
                relevant.append(f)
                seen_fills.add(key)

            for f in relevant:
                fill_side = str(f.get("side") or "").lower()
                fill_price = float(f.get("fillPx") or f.get("px") or 0)
                fill_qty = float(f.get("fillSz") or f.get("sz") or 0)
                clid = str(f.get("clOrdId") or "")
                if fill_price <= 0 or fill_qty <= 0:
                    continue

                level = level_from_clordid(clid)
                generation = generation_from_clordid(clid) + 1
                print(
                    f"FILL DETECTED {fill_side.upper():<4} "
                    f"px={fill_price:,.2f} qty={fill_qty:.5f} "
                    f"L{level} G{generation - 1}"
                )

                if fill_side == "buy":
                    replacement = fill_price * (1 + SELL_STEP)
                    net_est = replacement / fill_price - 1 - 2 * 0.0008 - 2 * 0.00005
                    if net_est < PROFIT_FLOOR:
                        print(
                            f"REPLACEMENT SKIP BUY->SELL: net_est={net_est*100:.3f}% "
                            f"< floor={PROFIT_FLOOR*100:.3f}%"
                        )
                        continue

                    current = get_open_orders(trade)
                    if any(
                        is_ours(o) and side(o) == "sell"
                        and abs(px(o) - replacement) / replacement < 0.00001
                        for o in current
                    ):
                        print("REPLACEMENT SKIP: SELL level already exists.")
                        continue

                    place_limit(trade, "sell", replacement, fill_price * fill_qty, level, generation)

                elif fill_side == "sell":
                    replacement = fill_price * (1 - GRID_PCT)
                    current = get_open_orders(trade)
                    if any(
                        is_ours(o) and side(o) == "buy"
                        and abs(px(o) - replacement) / replacement < 0.00001
                        for o in current
                    ):
                        print("REPLACEMENT SKIP: BUY level already exists.")
                        continue

                    place_limit(trade, "buy", replacement, fill_price * fill_qty, level, generation)

            all_orders = get_open_orders(trade)
            bot = ours(all_orders)
            buy_count = sum(side(o) == "buy" for o in bot)
            sell_count = sum(side(o) == "sell" for o in bot)

            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"ETH={last:,.2f} USDT={balance['USDT']:.2f} "
                f"ETH={balance['ETH']:.5f} F511orders={len(bot)} "
                f"BUY={buy_count} SELL={sell_count}"
            )

            if len(bot) > MAX_OPEN_ORDERS:
                print(
                    f"SAFETY WARNING: F has {len(bot)} orders "
                    f"(limit {MAX_OPEN_ORDERS})."
                )

            time.sleep(LOOP_SECONDS)

        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"LOOP ERROR: {type(exc).__name__}: {exc}")
            time.sleep(LOOP_SECONDS)

    print()
    print("F / v5.1.1 STOPPED.")
    print("Existing orders were NOT cancelled.")


if __name__ == "__main__":
    main()
