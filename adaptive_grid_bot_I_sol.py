"""Bot I - SOL-USDT v5.1.1 safe demo runner.

Uses the validated v5.1.1 engine with SOL-specific balance handling.
Account/config: .env.v50 | OKX DEMO only | Prefix: I511
"""
import os
import time
from datetime import datetime
from dotenv import load_dotenv
import okx.Trade as Trade
import adaptive_grid_v0511_demo_smart_loop as base

ENV_FILE = ".env.v50"
PREFIX = "I511"
LOOP_SECONDS = 60
MAX_BUY_ORDERS = 5
MAX_SELL_ORDERS = 5
MAX_OPEN_ORDERS = 10

load_dotenv(ENV_FILE, override=True)
base.INST_ID = "SOL-USDT"
base.PREFIX = PREFIX
base.LOOP_SECONDS = LOOP_SECONDS
base.MAX_BUY_ORDERS = MAX_BUY_ORDERS
base.MAX_SELL_ORDERS = MAX_SELL_ORDERS
base.MAX_OPEN_ORDERS = MAX_OPEN_ORDERS


def get_sol_balance(account):
    r = account.get_account_balance(ccy="USDT,SOL")
    if r.get("code") != "0" or not r.get("data"):
        raise RuntimeError(f"Balance error: {r}")
    out = {"USDT": 0.0, "SOL": 0.0}
    for item in r["data"][0].get("details", []):
        ccy = item.get("ccy")
        if ccy in out:
            out[ccy] = float(item.get("availBal") or item.get("cashBal") or 0)
    return out


def safe_place_limit(trade, side_name, price, usdt_size, level, generation):
    current = base.ours(base.get_open_orders(trade))
    if len(current) >= MAX_OPEN_ORDERS:
        print(f"[I SAFETY] Skip: {len(current)}/{MAX_OPEN_ORDERS} I511 orders.")
        return False
    qty = usdt_size / price
    clid = base.make_clordid(side_name, level, generation)
    if any(str(o.get("clOrdId") or "") == clid for o in current):
        print(f"[I SAFETY] Duplicate skipped: {clid}")
        return False
    params = {"instId": base.INST_ID, "tdMode": base.TD_MODE,
              "side": side_name, "ordType": "limit", "clOrdId": clid,
              "px": base.fmt_price(price), "sz": base.fmt_qty(qty),
              "pxAmendType": "1"}
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

base.get_balance = get_sol_balance
base.place_limit = safe_place_limit


def main():
    print("=" * 76)
    print("      ADAPTIVE GRID BOT I | SOL-USDT v5.1.1")
    print("      .env.v50 | OKX DEMO | I511")
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
    market, account, trade = base.api_init()
    last = base.get_last_price(market)
    balance = get_sol_balance(account)
    all_orders = base.get_open_orders(trade)
    bot = base.ours(all_orders)
    print(f"SOL price    : ${last:,.2f}")
    print(f"USDT avail   : {balance['USDT']:.4f}")
    print(f"SOL avail    : {balance['SOL']:.8f}")
    print(f"All SPOT orders: {len(all_orders)}")
    print(f"I511 orders  : {len(bot)}")
    print()
    if not enabled:
        print("READ ONLY CHECK PASSED.")
        return
    anchor = base.nearest_anchor_from_existing(bot, last)
    print(f"GRID ANCHOR  : ${anchor:,.1f}")
    if not bot:
        print("INITIAL GRID")
        for s, p, level, generation in base.build_initial_grid(anchor):
            if s == "sell":
                need = base.ORDER_USDT / p
                if balance["SOL"] < need:
                    print("STOP: insufficient SOL for initial SELL grid.")
                    break
                if safe_place_limit(trade, s, p, base.ORDER_USDT, level, generation):
                    balance["SOL"] -= need
            else:
                if balance["USDT"] < base.ORDER_USDT:
                    print("STOP: insufficient USDT for initial BUY grid.")
                    break
                if safe_place_limit(trade, s, p, base.ORDER_USDT, level, generation):
                    balance["USDT"] -= base.ORDER_USDT
        bot = base.ours(base.get_open_orders(trade))
    print()
    print("SMART LOOP ACTIVE.")
    print("Fills are reconciled from OKX before replacement orders.")
    print("Existing orders are NOT cancelled.")
    seen_fills = set()
    cycle = 0
    while base.running:
        cycle += 1
        print("=" * 76)
        print(f" SMART LOOP CYCLE {cycle} | BOT I | SOL-USDT | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 76)
        try:
            last = base.get_last_price(market)
            balance = get_sol_balance(account)
            fills = base.get_fills_since(trade)
            for f in fills:
                clid = str(f.get("clOrdId") or "")
                if not clid.startswith(PREFIX):
                    continue
                key = str(f.get("tradeId") or f.get("fillId") or "") or f"{clid}:{f.get('fillPx')}:{f.get('fillSz')}"
                if key in seen_fills:
                    continue
                seen_fills.add(key)
                fill_side = str(f.get("side") or "").lower()
                fill_price = float(f.get("fillPx") or f.get("px") or 0)
                fill_qty = float(f.get("fillSz") or f.get("sz") or 0)
                if fill_price <= 0 or fill_qty <= 0:
                    continue
                level = base.level_from_clordid(clid)
                generation = base.generation_from_clordid(clid) + 1
                print(f"FILL DETECTED {fill_side.upper():<4} px={fill_price:,.1f} qty={fill_qty:.6f} L{level} G{generation-1}")
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
            print(f"SOL={last:,.2f} USDT={balance['USDT']:.2f} SOL={balance['SOL']:.6f} I511orders={len(bot)} BUY={buys} SELL={sells}")
            if len(bot) > MAX_OPEN_ORDERS:
                print(f"SAFETY WARNING: I511 has {len(bot)} orders (limit {MAX_OPEN_ORDERS}).")
            time.sleep(LOOP_SECONDS)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"LOOP ERROR: {type(exc).__name__}: {exc}")
            time.sleep(LOOP_SECONDS)
    print("I v5.1.1 STOPPED.")
    print("Existing orders were NOT cancelled.")


if __name__ == "__main__":
    main()
