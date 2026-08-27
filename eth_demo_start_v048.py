import argparse
import os
from decimal import Decimal, ROUND_DOWN
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


def build_orders(market, account):
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
    grid = build_grid(price, distance, GRID_LEVELS_UP, GRID_LEVELS_DOWN)
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

    # Spot sells require available ETH. Keep only sells that the demo account can cover.
    filtered = []
    sell_reserved = Decimal('0')
    for o in orders:
        if o['side'] == 'sell':
            if bal['ETH'] - sell_reserved >= o['sz']:
                sell_reserved += o['sz']
                filtered.append(o)
        else:
            filtered.append(o)

    return info, price, trend, atr, distance, bal, filtered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-demo', action='store_true', help='Actually submit validated orders to OKX DEMO')
    args = parser.parse_args()

    if os.getenv('OKX_LIVE', '0') == '1':
        raise RuntimeError('LIVE GATE BLOCKED: OKX_LIVE must not be enabled')

    market, account, trade = api_init()
    info, price, trend, atr, distance, bal, orders = build_orders(market, account)

    print('=' * 76)
    print('ETH-USDT ADAPTIVE GRID BOT v4.8 | DEMO START')
    print('OKX DEMO ONLY')
    print('=' * 76)
    print(f'Price            : {price}')
    print(f'Trend            : {trend}')
    print(f'ATR30D           : {atr}')
    print(f'Grid distance    : {distance}')
    print(f'Tick size        : {info["tickSz"]}')
    print(f'Lot size         : {info["lotSz"]}')
    print(f'Min size         : {info["minSz"]}')
    print(f'Available USDT   : {bal["USDT"]}')
    print(f'Available ETH    : {bal["ETH"]}')
    print(f'Orders validated : {len(orders)}')
    for i, o in enumerate(orders, 1):
        print(f"  {i:02d} {o['side'].upper():4} L{o['level']:+d} px={o['px']} sz={o['sz']}")

    if not args.execute_demo:
        print('\nDRY RUN: no orders submitted.')
        print('To submit this validated grid to OKX DEMO, run with --execute-demo')
        return

    # Explicit user-requested DEMO execution. Never runs against production because FLAG='1'.
    if len(orders) == 0:
        raise RuntimeError('No valid orders to submit')

    print('\nEXECUTING VALIDATED GRID ON OKX DEMO...')
    results = []
    for idx, o in enumerate(orders, 1):
        side = o['side']
        clid = f"ETHV48{'B' if side == 'buy' else 'S'}{idx:02d}"
        response = trade.place_order(
            instId=INST_ID,
            tdMode='cash',
            clOrdId=clid,
            side=side,
            ordType='limit',
            px=str(o['px']),
            sz=str(o['sz']),
        )
        results.append((clid, response))
        print(f'  {idx:02d} {o["side"].upper():4} L{o["level"]:+d} -> {response}')

    print('\nDEMO GRID SUBMISSION COMPLETE')
    print(f'Orders attempted : {len(results)}')
    print('Production/live   : NOT USED (flag=1)')
    print('Next              : inspect open orders / fills before enabling a monitor loop')


if __name__ == '__main__':
    main()
