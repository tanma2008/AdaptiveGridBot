"""Bot F - ETH-USDT v5.1.1 safe runner.

Account/config: .env.v50 | OKX DEMO only
Prefix: F511

F is the ETH v5.1.1 bot. It reuses the v5.1.1 grid engine but provides
ETH-specific balance/reporting plus the same safety guards used by C.
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv
import okx.Trade as Trade

import adaptive_grid_v0511_demo_smart_loop as base

ENV_FILE = ".env.v50"
PREFIX = "F511"
MAX_OPEN_ORDERS = 10
LOOP_SECONDS = 60

load_dotenv(ENV_FILE, override=True)
base.INST_ID = "ETH-USDT"
base.PREFIX = PREFIX
base.LOOP_SECONDS = LOOP_SECONDS
base.MAX_OPEN_ORDERS = MAX_OPEN_ORDERS


def get_eth_balance(account):
    r = account.get_account_balance(ccy="USDT,ETH")
    if r.get("code") != "0" or not r.get("data"):
        raise RuntimeError(f"Balance error: {r}")
    out = {"USDT": 0.0, "ETH": 0.0}
    for item in r["data"][0].get("details", []):
        ccy = item.get("ccy")
        if ccy in out:
            out[ccy] = float(item.get("availBal") or item.get("cashBal") or 0)
    return out


def _fill_key(fill):
    trade_id = str(fill.get("tradeId") or fill.get("fillId") or "")
    return trade_id or (
        f"{fill.get('clOrdId','')}|{fill.get('fillPx') or fill.get('px')}|"
        f"{fill.get('fillSz') or fill.get('sz')}|{fill.get('ts') or ''}"
    )


market = None
account = None
trade = None
_BASELINE_FILL_KEYS = set()
_PROCESSED_CLIDS = set()


def get_new_fills(trade):
    fills = base.get_fills_since(trade)
    current = base.get_open_orders(trade)
    open_clids = {str(o.get("clOrdId") or "") for o in current if base.is_ours(o)}
    out = []
    for fill in fills:
        clid = str(fill.get("clOrdId") or "")
        if not clid.startswith(PREFIX) or _fill_key(fill) in _BASELINE_FILL_KEYS:
            continue
        if clid in open_clids or clid in _PROCESSED_CLIDS:
            continue
        _PROCESSED_CLIDS.add(clid)
        out.append(fill)
    return out


def safe_place_limit(trade, side_name, price, usdt_size, level, generation):
    current = base.get_open_orders(trade)
    bot_orders = [o for o in current if base.is_ours(o)]
    if len(bot_orders) >= MAX_OPEN_ORDERS:
        print(f"[F SAFETY] Skip {side_name.upper()} ${price:,.1f}: {len(bot_orders)}/{MAX_OPEN_ORDERS} F511 orders.")
        return False
    qty = usdt_size / price
    clid = base.make_clordid(side_name, level, generation)
    if any(str(o.get("clOrdId") or "") == clid or (base.side(o) == side_name and abs(base.px(o) - price) / max(price, 1.0) < 0.00001) for o in bot_orders):
        print(f"[F SAFETY] Duplicate skipped: {clid}")
        return False
    params = {
        "instId": base.INST_ID, "tdMode": base.TD_MODE, "side": side_name,
        "ordType": "limit", "clOrdId": clid, "px": base.fmt_price(price),
        "sz": base.fmt_qty(qty), "pxAmendType": "1",
    }
    r = trade._request_with_params(Trade.POST, Trade.PLACR_ORDER, params)
    if r.get("code") != "0":
        print(f"ORDER ERROR {side_name} {price:.1f}: {r}")
        return False
    data = r.get("data") or []
    item = data[0] if data else {}
    if item.get("sCode") not in (None, "", "0"):
        print(f"ORDER ERROR {side_name} {price:.1f}: {r}")
        return False
    print(f"ORDER {side_name:<4} ${usdt_size:7.2f} px={price:,.1f} qty={qty:.6f} L{level} G{generation} clOrdId={clid} ordId={item.get('ordId','')}")
    return True


base.place_limit = safe_place_limit

def main():
    print("=" * 76)
    print("      ADAPTIVE GRID BOT F | ETH-USDT v5.1.1")
    print("      .env.v50 | OKX DEMO | F511")
    print("=" * 76)
    print(f"Grid         : {base.GRID_PCT * 100:.2f}%")
    print(f"Order size   : ${base.ORDER_USDT:.2f}")
    print(f"SELL mult.   : {base.SELL_MULT:.2f}x")
    print(f"Profit floor : {base.PROFIT_FLOOR * 100:.2f}%")
    print(f"Loop         : {LOOP_SECONDS} seconds")
    enabled = os.getenv("V50_ENABLE_ORDERS", "NO").upper() == "YES"
    print("ORDER MODE   : " + ("DEMO ORDERS ENABLED" if enabled else "READ ONLY"))
    print("OKX API FLAG : 1 (DEMO)")
    print()
    global market, account, trade, _BASELINE_FILL_KEYS
    market, account, trade = base.api_init()
    baseline = base.get_fills_since(trade)
    _BASELINE_FILL_KEYS = {_fill_key(f) for f in baseline if str(f.get("clOrdId") or "").startswith(PREFIX)}
    print(f"Historical F511 fills ignored: {len(_BASELINE_FILL_KEYS)}")
    last = base.get_last_price(market)
    balance = get_eth_balance(account)
    all_orders = base.get_open_orders(trade)
    bot = base.ours(all_orders)
    print(f"ETH price    : ${last:,.2f}")
    print(f"USDT avail   : {balance['USDT']:.4f}")
    print(f"ETH avail    : {balance['ETH']:.8f}")
    print(f"All SPOT orders: {len(all_orders)}")
    print(f"F511 orders  : {len(bot)}")
    print()
    if not enabled:
        print("READ ONLY CHECK PASSED.")
        return
    anchor = base.nearest_anchor_from_existing(bot, last)
    print(f"GRID ANCHOR  : ${anchor:,.1f}")
    if not bot:
        print("INITIAL GRID")
        for side_name, price, level, generation in base.build_initial_grid(anchor):
            if side_name == "sell":
                need = base.ORDER_USDT / price
                if balance["ETH"] < need:
                    print("STOP: insufficient ETH for initial SELL grid.")
                    break
                if safe_place_limit(trade, side_name, price, base.ORDER_USDT, level, generation):
                    balance["ETH"] -= need
            else:
                if balance["USDT"] < base.ORDER_USDT:
                    print("STOP: insufficient USDT for initial BUY grid.")
                    break
                if safe_place_limit(trade, side_name, price, base.ORDER_USDT, level, generation):
                    balance["USDT"] -= base.ORDER_USDT
        bot = base.ours(base.get_open_orders(trade))
    print()
    print("SMART LOOP ACTIVE.")
    print("Fills are reconciled from OKX before replacement orders.")
    print("Existing orders are NOT cancelled.")
    seen = set()
    cycle = 0
    while base.running:
        cycle += 1
        print()
        print("=" * 76)
        print(f" SMART LOOP CYCLE {cycle} | BOT F | ETH-USDT | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 76)
        try:
            last = base.get_last_price(market)
            balance = get_eth_balance(account)
            fills = get_new_fills(trade)
            for f in fills:
                fill_side = str(f.get("side") or "").lower()
                fill_price = float(f.get("fillPx") or f.get("px") or 0)
                fill_qty = float(f.get("fillSz") or f.get("sz") or 0)
                clid = str(f.get("clOrdId") or "")
                key = _fill_key(f)
                if key in seen or fill_price <= 0 or fill_qty <= 0:
                    continue
                seen.add(key)
                level = base.level_from_clordid(clid)
                generation = base.generation_from_clordid(clid) + 1
                print(f"FILL DETECTED {fill_side.upper():<4} px={fill_price:,.1f} qty={fill_qty:.6f} L{level} G{generation - 1}")
                if fill_side == "buy":
                    replacement = fill_price * (1 + base.SELL_STEP)
                    net_est = replacement / fill_price - 1 - 2 * 0.0008 - 2 * 0.00005
                    if net_est < base.PROFIT_FLOOR:
                        print(f"REPLACEMENT SKIP BUY->SELL: net_est={net_est*100:.3f}% < floor={base.PROFIT_FLOOR*100:.3f}%")
                        continue
                    current = base.get_open_orders(trade)
                    if any(base.is_ours(o) and base.side(o) == "sell" and abs(base.px(o)-replacement)/replacement < 0.00001 for o in current):
                        print("REPLACEMENT SKIP: SELL level already exists.")
                        continue
                    safe_place_limit(trade, "sell", replacement, fill_price * fill_qty, level, generation)
                elif fill_side == "sell":
                    replacement = fill_price * (1 - base.GRID_PCT)
                    current = base.get_open_orders(trade)
                    if any(base.is_ours(o) and base.side(o) == "buy" and abs(base.px(o)-replacement)/replacement < 0.00001 for o in current):
                        print("REPLACEMENT SKIP: BUY level already exists.")
                        continue
                    safe_place_limit(trade, "buy", replacement, fill_price * fill_qty, level, generation)
            bot = base.ours(base.get_open_orders(trade))
            buys = sum(base.side(o) == "buy" for o in bot)
            sells = sum(base.side(o) == "sell" for o in bot)
            print("=" * 76)
            print(f" BOT F | ETH-USDT | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 76)
            print(f"Price          : ${last:,.2f}")
            print(f"USDT available : {balance['USDT']:.2f}")
            print(f"ETH available  : {balance['ETH']:.6f}")
            print(f"F511 orders    : {len(bot)} | BUY {buys} | SELL {sells}")
            if len(bot) > MAX_OPEN_ORDERS:
                print(f"SAFETY WARNING: F511 has {len(bot)} orders (limit {MAX_OPEN_ORDERS}).")
            import time
            time.sleep(LOOP_SECONDS)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"LOOP ERROR: {type(exc).__name__}: {exc}")
            import time
            time.sleep(LOOP_SECONDS)
    print()
    print("F v5.1.1 STOPPED.")
    print("Existing orders were NOT cancelled.")


if __name__ == "__main__":
    main()
