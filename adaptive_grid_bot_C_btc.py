"""Bot C - BTC-USDT v5.1.1 safe runner.

Work machine: D:\\AdaptiveGridBot
Account: dedicated C account via .env.v50
DEMO only.

Fixes applied only to C:
- Ignore all V511 fills that existed before this process started.
- Process each newly completed V511 order once.
- Never place above MAX_OPEN_ORDERS.
- Ask OKX to amend a price into its current allowed price band when needed.
"""

import os
from datetime import datetime

from dotenv import load_dotenv
import okx.Trade as Trade

import adaptive_grid_v0511_demo_smart_loop as base


ENV_FILE = ".env.v50"
PREFIX = "V511"
MAX_OPEN_ORDERS = 10

# Keep the original implementation untouched; C patches only the unsafe edges.
load_dotenv(ENV_FILE, override=True)
_market, _account, _trade = base.api_init()


def _fill_key(fill):
    trade_id = str(fill.get("tradeId") or fill.get("fillId") or "")
    if trade_id:
        return trade_id
    return (
        f"{fill.get('clOrdId','')}|{fill.get('fillPx') or fill.get('px')}|"
        f"{fill.get('fillSz') or fill.get('sz')}|{fill.get('ts') or ''}"
    )


# Snapshot the historical V511 fills BEFORE starting the smart loop.
# Those fills belong to previous sessions and must never trigger new orders.
_baseline_fills = base.get_fills_since(_trade)
_BASELINE_FILL_KEYS = {_fill_key(f) for f in _baseline_fills}
_PROCESSED_CLIDS = set()

_original_get_fills_since = base.get_fills_since
_original_place_limit = base.place_limit


def _get_new_fills(trade, after_ms=None):
    """Return only fills created after this C process started.

    A completed order is returned only once per client order id. This also
    prevents multiple partial-fill records for one order from spawning
    multiple replacement orders.
    """
    fills = _original_get_fills_since(trade, after_ms)
    current = base.get_open_orders(trade)
    open_clids = {
        str(o.get("clOrdId") or "")
        for o in current
        if base.is_ours(o)
    }

    out = []
    for fill in fills:
        clid = str(fill.get("clOrdId") or "")
        if not clid.startswith(PREFIX):
            continue
        if _fill_key(fill) in _BASELINE_FILL_KEYS:
            continue
        # Wait for the source order to disappear from open orders. That means
        # we reconcile a completed order, not a partial fill.
        if clid in open_clids:
            continue
        if clid in _PROCESSED_CLIDS:
            continue
        _PROCESSED_CLIDS.add(clid)
        out.append(fill)

    return out


def _safe_place_limit(trade, side_name, price, usdt_size, level, generation):
    """Place one C order with a hard 10-order ceiling and OKX price amend."""
    current = base.get_open_orders(trade)
    bot_orders = [o for o in current if base.is_ours(o)]

    if len(bot_orders) >= MAX_OPEN_ORDERS:
        print(
            f"[C SAFETY] Skip {side_name.upper()} ${price:,.1f}: "
            f"already {len(bot_orders)}/{MAX_OPEN_ORDERS} V511 orders."
        )
        return False

    qty = usdt_size / price
    clid = base.make_clordid(side_name, level, generation)

    # Exact duplicate guard before sending the request.
    if any(
        str(o.get("clOrdId") or "") == clid
        or (
            base.side(o) == side_name
            and abs(base.px(o) - price) / max(price, 1.0) < 0.00001
        )
        for o in bot_orders
    ):
        print(f"[C SAFETY] Duplicate skipped: {clid}")
        return False

    params = {
        "instId": base.INST_ID,
        "tdMode": base.TD_MODE,
        "side": side_name,
        "ordType": "limit",
        "clOrdId": clid,
        "px": base.fmt_price(price),
        "sz": base.fmt_qty(qty),
        # OKX supports automatic price amendment when px exceeds the
        # dynamically calculated price-limit band.
        "pxAmendType": "1",
    }

    r = trade._request_with_params(
        Trade.POST,
        Trade.PLACR_ORDER,
        params,
    )

    if r.get("code") != "0":
        print(f"ORDER ERROR {side_name} {price:.1f}: {r}")
        return False

    data = r.get("data") or []
    item = data[0] if data else {}
    if item.get("sCode") not in (None, "", "0"):
        print(f"ORDER ERROR {side_name} {price:.1f}: {r}")
        return False

    oid = item.get("ordId", "")
    print(
        f"ORDER {side_name:<4} ${usdt_size:7.2f} "
        f"px={price:,.1f} qty={qty:.6f} "
        f"L{level} G{generation} clOrdId={clid} ordId={oid}"
    )
    return True


# Patch only the imported module instance used by base.main().
base.get_fills_since = _get_new_fills
base.place_limit = _safe_place_limit
base.MAX_OPEN_ORDERS = MAX_OPEN_ORDERS


if __name__ == "__main__":
    print("=" * 76)
    print("      ADAPTIVE GRID BOT C | v5.1.1 SAFE PATCH")
    print("      BTC-USDT | .env.v50 | OKX DEMO | Account C")
    print("=" * 76)
    print(f"Startup historical V511 fills ignored: {len(_BASELINE_FILL_KEYS)}")
    print("Fixes: historical-fill guard | one replacement/order | max 10 | pxAmendType=1")
    print()
    base.main()
