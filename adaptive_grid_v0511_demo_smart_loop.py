"""
ADAPTIVE GRID BOT v5.1.1 - OKX DEMO SMART LOOP
Persistent grid + real OKX fill reconciliation.

Candidate E:
  Grid       : 0.60%
  Order size : $20
  SELL mult  : 2.50x
  Profit floor: 0.27%

Safety:
- OKX Demo only (flag=1)
- .env.v50
- V50_ENABLE_ORDERS=NO => read-only
- No automatic cancellation
- Only manages V51.1 client order IDs
- Reconciles fills from OKX before creating replacements
- Maintains at most 10 active V51 orders
- Does NOT move the anchor every loop
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
INST_ID = "BTC-USDT"
BOT_LABEL = "C"
TD_MODE = "cash"
PREFIX = "V511"

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
    print("Stopping v5.1.1 safely.")
    print("Existing orders are NOT cancelled.")


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is missing in {ENV_FILE}")
    return value


def fmt_price(p):
    return f"{p:.1f}"


def fmt_qty(q):
    return f"{q:.6f}"


def api_init():
    api_key = require_env("OKX_API_KEY")
    secret = require_env("OKX_SECRET_KEY")
    passphrase = require_env("OKX_PASSPHRASE")

    flag = "1"

    market = MarketData.MarketAPI(
        api_key, secret, passphrase, False, flag
    )
    account = Account.AccountAPI(
        api_key, secret, passphrase, False, flag
    )
    trade = Trade.TradeAPI(
        api_key, secret, passphrase, False, flag
    )
    return market, account, trade


def get_last_price(market):
    r = market.get_ticker(instId=INST_ID)
    if r.get("code") != "0" or not r.get("data"):
        raise RuntimeError(f"Ticker error: {r}")
    return float(r["data"][0]["last"])


def get_balance(account):
    r = account.get_account_balance(ccy="USDT,BTC")
    if r.get("code") != "0" or not r.get("data"):
        raise RuntimeError(f"Balance error: {r}")

    out = {"USDT": 0.0, "BTC": 0.0}
    for item in r["data"][0].get("details", []):
        ccy = item.get("ccy")
        if ccy in out:
            out[ccy] = float(
                item.get("availBal")
                or item.get("cashBal")
                or 0
            )
    return out


def get_open_orders(trade):
    r = trade.get_order_list(instType="SPOT")
    if r.get("code") != "0":
        raise RuntimeError(f"Open order error: {r}")

    return [
        o for o in r.get("data", [])
        if o.get("instId") == INST_ID
    ]


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


def sz(o):
    try:
        return float(o.get("sz") or 0)
    except Exception:
        return 0.0


def make_clordid(side_name, level, generation):
    # <= 32 chars and stable/readable.
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

    # Direct request: the installed SDK has an empty stpMode default which
    # caused OKX 51000 in the first v5.0 version.
    r = trade._request_with_params(
        Trade.POST,
        Trade.PLACR_ORDER,
        params,
    )

    if r.get("code") != "0":
        print(f"ORDER ERROR {side_name} {price:.1f}: {r}")
        return False

    data = r.get("data") or []
    oid = data[0].get("ordId", "") if data else ""

    print(
        f"ORDER {side_name:<4} "
        f"${usdt_size:7.2f} "
        f"px={price:,.1f} "
        f"qty={qty:.6f} "
        f"L{level} G{generation} "
        f"clOrdId={clid} ordId={oid}"
    )
    return True


def build_initial_grid(anchor):
    levels = []

    for level in range(1, MAX_SELL_ORDERS + 1):
        levels.append(
            ("sell", anchor * (1 + SELL_STEP * level), level, 0)
        )

    for level in range(1, MAX_BUY_ORDERS + 1):
        levels.append(
            ("buy", anchor * (1 - GRID_PCT * level), level, 0)
        )

    return levels


def nearest_anchor_from_existing(order_list, fallback):
    prices = [px(o) for o in order_list if px(o) > 0]
    if not prices:
        return fallback
    # Existing orders are authoritative after restart.
    return sum(prices) / len(prices)


def get_fills_since(trade, after_ms=None):
    # get_fills() is supported by the installed OKX SDK.
    kwargs = {"instType": "SPOT"}
    if after_ms is not None:
        kwargs["beginId"] = str(after_ms)

    r = trade.get_fills(**kwargs)

    if r.get("code") != "0":
        raise RuntimeError(f"Fills error: {r}")

    return r.get("data", [])


def print_header():
    print("=" * 76)
    print(f"      ADAPTIVE GRID BOT {BOT_LABEL} | {INST_ID} v5.1.1")
    print(f"      OKX DEMO | ACCOUNT {BOT_LABEL} | SAFE RECONCILE")
    print("=" * 76)
    print(f"Check interval : {LOOP_SECONDS} seconds")
    print("Mode           : OKX DEMO ONLY")
    print("Behavior       : SAFE RECONCILE")
    print("Ctrl+C         : STOP")
    print(f"Grid           : {GRID_PCT * 100:.2f}%")
    print(f"Order size     : ${ORDER_USDT:.2f}")
    print(f"SELL mult.     : {SELL_MULT:.2f}x")
    print(f"Profit floor   : {PROFIT_FLOOR * 100:.2f}%")
    print(f"Prefix         : {PREFIX}")
    print()


def main():
    print_header()

    load_dotenv(ENV_FILE, override=True)

    enabled = os.getenv("V50_ENABLE_ORDERS", "NO").upper() == "YES"

    print(
        "ORDER MODE   : "
        + ("DEMO ORDERS ENABLED" if enabled else "READ ONLY")
    )
    print("OKX API FLAG : 1 (DEMO)")
    print()

    market, account, trade = api_init()

    last = get_last_price(market)
    balance = get_balance(account)
    all_orders = get_open_orders(trade)
    bot = ours(all_orders)

    print(f"BTC price    : ${last:,.2f}")
    print(f"USDT avail   : {balance['USDT']:.4f}")
    print(f"BTC avail    : {balance['BTC']:.8f}")
    print(f"All SPOT orders: {len(all_orders)}")
    print(f"V5.1.1 orders : {len(bot)}")
    print()

    if not enabled:
        print("READ ONLY CHECK PASSED.")
        print(
            "Set V50_ENABLE_ORDERS=YES in .env.v50 "
            "only when ready to place Demo orders."
        )
        return

    anchor = nearest_anchor_from_existing(bot, last)
    print(f"GRID ANCHOR  : ${anchor:,.1f}")
    print()

    # If no V511 orders exist, create exactly one initial grid.
    if not bot:
        print("INITIAL GRID")
        for s, p, level, generation in build_initial_grid(anchor):
            if s == "sell":
                if balance["BTC"] < ORDER_USDT / p:
                    print("STOP: insufficient BTC for initial SELL grid.")
                    break
                if place_limit(trade, s, p, ORDER_USDT, level, generation):
                    balance["BTC"] -= ORDER_USDT / p
            else:
                if balance["USDT"] < ORDER_USDT:
                    print("STOP: insufficient USDT for initial BUY grid.")
                    break
                if place_limit(trade, s, p, ORDER_USDT, level, generation):
                    balance["USDT"] -= ORDER_USDT

        all_orders = get_open_orders(trade)
        bot = ours(all_orders)

    # Fills already seen in this process, keyed by order id.
    seen_fills = set()
    cycle = 0

    print()
    print("SMART LOOP ACTIVE.")
    print("Fills are reconciled from OKX before replacement orders.")
    print("Existing orders are NOT cancelled.")
    print()

    while running:
        cycle += 1
        print()
        print("=" * 76)
        print(f" SMART LOOP CYCLE {cycle} | BOT {BOT_LABEL} | {INST_ID} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 76)
        try:
            last = get_last_price(market)
            balance = get_balance(account)
            all_orders = get_open_orders(trade)
            bot = ours(all_orders)

            # ----------------------------------------------------------
            # REAL FILL RECONCILIATION
            # ----------------------------------------------------------
            fills = get_fills_since(trade)

            relevant = []
            for f in fills:
                clid = str(f.get("clOrdId") or "")
                if not clid.startswith(PREFIX):
                    continue

                fill_id = str(f.get("tradeId") or f.get("fillId") or "")
                key = (
                    fill_id
                    or f"{clid}:{f.get('fillPx')}:{f.get('fillSz')}"
                )

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
                    f"px={fill_price:,.1f} "
                    f"qty={fill_qty:.6f} "
                    f"L{level} G{generation - 1}"
                )

                # Replace BUY with SELL above actual fill price.
                if fill_side == "buy":
                    replacement = fill_price * (1 + SELL_STEP)

                    # Require the intended spread to clear the floor.
                    net_est = (
                        replacement / fill_price
                        - 1
                        - 2 * 0.0008
                        - 2 * 0.00005
                    )

                    if net_est < PROFIT_FLOOR:
                        print(
                            f"REPLACEMENT SKIP BUY->SELL: "
                            f"net_est={net_est*100:.3f}% "
                            f"< floor={PROFIT_FLOOR*100:.3f}%"
                        )
                        continue

                    # Never duplicate a replacement price.
                    current = get_open_orders(trade)
                    if any(
                        is_ours(o)
                        and side(o) == "sell"
                        and abs(px(o) - replacement) / replacement < 0.00001
                        for o in current
                    ):
                        print("REPLACEMENT SKIP: SELL level already exists.")
                        continue

                    place_limit(
                        trade,
                        "sell",
                        replacement,
                        fill_price * fill_qty,
                        level,
                        generation,
                    )

                # Replace SELL with BUY below actual fill price.
                elif fill_side == "sell":
                    replacement = fill_price * (1 - GRID_PCT)

                    current = get_open_orders(trade)
                    if any(
                        is_ours(o)
                        and side(o) == "buy"
                        and abs(px(o) - replacement) / replacement < 0.00001
                        for o in current
                    ):
                        print("REPLACEMENT SKIP: BUY level already exists.")
                        continue

                    place_limit(
                        trade,
                        "buy",
                        replacement,
                        fill_price * fill_qty,
                        level,
                        generation,
                    )

            # ----------------------------------------------------------
            # MAINTENANCE / SAFETY
            # ----------------------------------------------------------
            all_orders = get_open_orders(trade)
            bot = ours(all_orders)

            buy_count = sum(side(o) == "buy" for o in bot)
            sell_count = sum(side(o) == "sell" for o in bot)

            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"BTC={last:,.1f} "
                f"USDT={balance['USDT']:.2f} "
                f"BTC={balance['BTC']:.6f} "
                f"V5.1.1orders={len(bot)} "
                f"BUY={buy_count} SELL={sell_count}"
            )

            # Do not auto-fill missing levels here. Missing levels must be
            # caused by a real fill and reconciled above. This prevents the
            # v5.0 bug where every loop created new orders.

            if len(bot) > MAX_OPEN_ORDERS:
                print(
                    f"SAFETY WARNING: V5.1.1 has {len(bot)} orders "
                    f"(limit {MAX_OPEN_ORDERS})."
                )

            time.sleep(LOOP_SECONDS)

        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(
                f"LOOP ERROR: {type(exc).__name__}: {exc}"
            )
            time.sleep(LOOP_SECONDS)

    print()
    print("V5.1.1 STOPPED.")
    print("Existing orders were NOT cancelled.")


if __name__ == "__main__":
    main()
