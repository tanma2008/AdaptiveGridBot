import argparse
import os
import time
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from okx import Account, MarketData, Trade
from eth_grid_engine_v048 import (
    FILE_1H, FILE_1D, ATR_MULTIPLIER, GRID_LEVELS_UP, GRID_LEVELS_DOWN,
    calculate_ema, calculate_atr, determine_trend, build_grid,
    calculate_position_sizing, evaluate_risk,
)

load_dotenv(Path(__file__).with_name('.env'))
INST_ID = 'ETH-USDT'
FLAG = '1'  # OKX DEMO
MAX_EXPOSURE = Decimal('500')
PREFIX = 'ETHV48'


def env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f'Missing environment variable: {name}')
    return value


def qdown(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def api_init():
    key, secret, passphrase = env('OKX_API_KEY'), env('OKX_SECRET_KEY'), env('OKX_PASSPHRASE')
    market = MarketData.MarketAPI(key, secret, passphrase, False, FLAG)
    account = Account.AccountAPI(key, secret, passphrase, False, FLAG)
    trade = Trade.TradeAPI(key, secret, passphrase, False, FLAG)
    return market, account, trade


def balances(account):
    result = account.get_account_balance()
    if result.get('code') != '0':
        raise RuntimeError(f'Account balance failed: {result}')
    out = {'USDT': Decimal('0'), 'ETH': Decimal('0')}
    details = result.get('data', [{}])[0].get('details', [])
    for item in details:
        ccy = item.get('ccy')
        if ccy in out:
            out[ccy] = Decimal(item.get('availBal') or item.get('cashBal') or '0')
    return out



class OrderManager:
    """Reconcile the ETH v4.8 target grid against OKX DEMO open orders."""

    def __init__(self, trade):
        self.trade = trade

    def get_open_orders(self):
        response = self.trade.get_order_list(instType='SPOT', instId=INST_ID)
        if response.get('code') != '0':
            raise RuntimeError(f'Open orders lookup failed: {response}')
        return response.get('data', [])

    def cancel_order(self, order):
        response = self.trade.cancel_order(instId=INST_ID, ordId=str(order['ordId']))
        if response.get('code') != '0':
            raise RuntimeError(f'Cancel order failed: {response}')
        return response

    def place_order(self, order, clid):
        params = {
            'instId': INST_ID,
            'tdMode': 'cash',
            'clOrdId': clid,
            'side': order['side'],
            'ordType': 'limit',
            'px': str(order['px']),
            'sz': str(order['sz']),
        }
        try:
            # The installed SDK's place_order() has an invalid stpMode default;
            # use the already-proven direct authenticated request path instead.
            response = self.trade._request_with_params(Trade.POST, Trade.PLACR_ORDER, params)
        except Exception as exc:
            raise RuntimeError(f'OKX Place Order Exception: {type(exc).__name__}: {exc}')
        if response.get('code') != '0':
            raise RuntimeError(f'OKX Place Order Error: {response}')
        return response

    @staticmethod
    def client_id(order, index):
        return f"{PREFIX}{'B' if order['side'] == 'buy' else 'S'}{index:02d}"

    @staticmethod
    def same_order(existing, target):
        return (
            existing.get('side') == target['side']
            and Decimal(existing.get('px', '0')) == target['px']
            and Decimal(existing.get('sz', '0')) == target['sz']
        )

    def reconcile(self, targets, execute=False, open_orders=None):
        if open_orders is None:
            open_orders = self.get_open_orders()
        managed = {o.get('clOrdId'): o for o in open_orders if o.get('clOrdId', '').startswith(PREFIX)}
        target_map = {}
        actions = []

        for index, target in enumerate(targets, 1):
            clid = self.client_id(target, index)
            target_map[clid] = target
            existing = managed.get(clid)
            if existing and self.same_order(existing, target):
                actions.append((clid, 'KEEP', existing))
            elif existing:
                actions.append((clid, 'REPLACE', (existing, target)))
            else:
                actions.append((clid, 'PLACE', target))

        for clid, existing in managed.items():
            if clid not in target_map:
                actions.append((clid, 'STALE', existing))

        if not execute:
            return open_orders, actions

        results = []
        for clid, action, order in actions:
            if action == 'STALE':
                results.append((clid, 'CANCEL', self.cancel_order(order)))
            elif action == 'REPLACE':
                existing, target = order
                self.cancel_order(existing)
                results.append((clid, 'REPLACE', self.place_order(target, clid)))
            elif action == 'PLACE':
                results.append((clid, 'PLACE', self.place_order(order, clid)))
            else:
                results.append((clid, action, order))
        return open_orders, results

def build_orders(market, account, existing_orders=None):
    instruments = account.get_instruments(instType='SPOT')
    if instruments.get('code') != '0':
        raise RuntimeError(f'Instrument lookup failed: {instruments}')
    info = next((x for x in instruments.get('data', []) if x.get('instId') == INST_ID), None)
    if not info:
        raise RuntimeError(f'{INST_ID} instrument not found')
    if info.get('state') != 'live':
        raise RuntimeError(f'{INST_ID} state is {info.get("state")}')

    tick = Decimal(info['tickSz'])
    lot = Decimal(info['lotSz'])
    min_sz = Decimal(info['minSz'])

    ticker = market.get_ticker(instId=INST_ID)
    if ticker.get('code') != '0':
        raise RuntimeError(f'Ticker failed: {ticker}')
    price = Decimal(ticker['data'][0]['last'])

    h = pd.read_csv(FILE_1H, parse_dates=['timestamp'])
    d = pd.read_csv(FILE_1D, parse_dates=['timestamp'])
    h['ema50'] = calculate_ema(h, 50)
    h['ema200'] = calculate_ema(h, 200)
    d['atr30'] = calculate_atr(d, 30)
    row = h.iloc[-1]
    atr = Decimal(str(d.iloc[-1]['atr30']))
    trend = determine_trend(row)
    sizing = calculate_position_sizing()
    risk = evaluate_risk(price, atr, trend, sizing)
    if risk['status'] != 'PASS':
        raise RuntimeError(f'RISK BLOCK: {risk}')

    distance = atr * Decimal(str(ATR_MULTIPLIER))

    # Preserve the existing grid anchor. Prefer the first BUY level (L-1),
    # then the first SELL level (L+1), so the exact existing price grid is
    # reconstructed instead of averaging rounded levels and causing churn.
    anchor = price
    managed = [
        o for o in (existing_orders or [])
        if o.get('clOrdId', '').startswith(PREFIX)
    ]
    anchor_candidates = []
    for o in managed:
        clid = o.get('clOrdId', '')
        try:
            side_code = clid[len(PREFIX)]
            index = int(clid[len(PREFIX) + 1:])
            if side_code == 'B' and 1 <= index <= 5:
                level = -index
                priority = index
            elif side_code == 'S' and 6 <= index <= 8:
                level = index - 5
                priority = 10 + level
            else:
                continue
            candidate = Decimal(str(o['px'])) - (Decimal(level) * distance)
            anchor_candidates.append((priority, candidate))
        except (KeyError, TypeError, ValueError, IndexError):
            continue

    if anchor_candidates:
        _, raw_anchor = min(anchor_candidates, key=lambda item: item[0])
        # Round to the instrument tick so the original grid prices are
        # reconstructed exactly despite ATR being a non-tick decimal.
        anchor = raw_anchor.quantize(tick, rounding=ROUND_HALF_UP)

    grid = build_grid(anchor, distance, GRID_LEVELS_UP, GRID_LEVELS_DOWN)
    bal = balances(account)

    orders = []
    total_buy_notional = Decimal('0')
    for _, g in grid.iterrows():
        raw_px = Decimal(str(g['price']))
        px = qdown(raw_px, tick)
        raw_qty = Decimal(str(sizing['order_size_usdt'])) / px
        qty = qdown(raw_qty, lot)
        if qty < min_sz:
            continue
        notional = px * qty
        side = g['side'].lower()
        if side == 'buy':
            total_buy_notional += notional
        orders.append({
            'side': side,
            'level': int(g['level']),
            'px': px,
            'sz': qty,
        })

    if total_buy_notional > MAX_EXPOSURE:
        raise RuntimeError(f'BUY exposure {total_buy_notional} exceeds cap {MAX_EXPOSURE}')

    filtered = []
    sell_reserved = Decimal('0')
    for o in orders:
        if o['side'] == 'sell':
            if bal['ETH'] - sell_reserved >= o['sz']:
                sell_reserved += o['sz']
                filtered.append(o)
        else:
            filtered.append(o)

    return info, price, trend, atr, distance, bal, anchor, filtered




def main():
    # BAT is the sole entry-point contract: no CLI options are required.
    # Bot D always runs the validated OKX DEMO reconciliation loop.
    execute_demo = True
    loop = True
    interval = 60

    if os.getenv('OKX_LIVE', '0') == '1':
        raise RuntimeError('LIVE GATE BLOCKED: OKX_LIVE must not be enabled')

    interval = max(60, interval)
    market, account, trade = api_init()
    manager = OrderManager(trade)
    cycle = 0

    while True:
        cycle += 1
        try:
            existing_open_orders = manager.get_open_orders()
            info, price, trend, atr, distance, bal, anchor, orders = build_orders(
                market, account, existing_open_orders
            )

            print()
            print('=' * 76)
            print(f'      ADAPTIVE GRID BOT D | ETH-USDT v4.8')
            print(f'      OKX DEMO | ACCOUNT D | SAFE RECONCILE')
            print('=' * 76)
            print(f'Cycle          : {cycle}')
            print('Mode           : OKX DEMO ONLY')
            print('Behavior       : SAFE RECONCILE')
            print('Ctrl+C         : STOP')
            print(f'Price            : {price}')
            print(f'Trend            : {trend}')
            print(f'ATR30D           : {atr}')
            print(f'Grid distance    : {distance}')
            print(f'Grid anchor      : {anchor}')
            print(f'Tick size        : {info["tickSz"]}')
            print(f'Lot size         : {info["lotSz"]}')
            print(f'Min size         : {info["minSz"]}')
            print(f'Available USDT   : {bal["USDT"]}')
            print(f'Available ETH    : {bal["ETH"]}')
            print(f'Orders validated : {len(orders)}')
            for i, o in enumerate(orders, 1):
                print(f"  {i:02d} {o['side'].upper():4} L{o['level']:+d} px={o['px']} sz={o['sz']}")

            open_orders, actions = manager.reconcile(
                orders, execute=execute_demo, open_orders=existing_open_orders
            )

            print(f'Open orders        : {len(open_orders)}')
            print('Order manager      : READY')
            for clid, action, _ in actions:
                print(f'  {clid:10} {action}')

            if execute_demo:
                print('DEMO ORDER RECONCILIATION COMPLETE')
                print(f'Actions processed  : {len(actions)}')
                print('Production/live    : NOT USED (flag=1)')
            else:
                print('DRY RUN: no order writes submitted.')

        except KeyboardInterrupt:
            print('\nLoop stopped by user.')
            break
        except Exception as exc:
            print(f'ERROR: {type(exc).__name__}: {exc}')
            if not loop:
                raise

        if not loop:
            break

        print(f'Next cycle in {interval} seconds...')
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print('\nLoop stopped by user.')
            break


if __name__ == '__main__':
    main()

