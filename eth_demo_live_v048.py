import os
from pathlib import Path
from decimal import Decimal
from dotenv import load_dotenv
from okx import Account, MarketData, Trade
from eth_grid_engine_v048 import build_grid, calculate_position_sizing, evaluate_risk, determine_trend, calculate_ema, calculate_atr, FILE_1H, FILE_1D, ATR_MULTIPLIER, GRID_LEVELS_UP, GRID_LEVELS_DOWN
from eth_order_manager_v048 import OrderManager, OrderIntent

load_dotenv(Path(__file__).with_name('.env'))
FLAG = '1'
INST_ID = 'ETH-USDT'


def env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f'Missing environment variable: {name}')
    return value


def api_init():
    key, secret, passphrase = env('OKX_API_KEY'), env('OKX_SECRET_KEY'), env('OKX_PASSPHRASE')
    market = MarketData.MarketAPI(key, secret, passphrase, False, FLAG)
    account = Account.AccountAPI(key, secret, passphrase, False, FLAG)
    trade = Trade.TradeAPI(key, secret, passphrase, False, FLAG)
    return market, account, trade


def main():
    if os.getenv('OKX_LIVE', '0') == '1':
        raise RuntimeError('LIVE GATE BLOCKED: OKX_LIVE must not be enabled')
    market, account, trade = api_init()
    ticker = market.get_ticker(instId=INST_ID)
    if ticker.get('code') != '0': raise RuntimeError(f'Ticker failed: {ticker}')
    price = Decimal(ticker['data'][0]['last'])

    h = __import__('pandas').read_csv(FILE_1H, parse_dates=['timestamp'])
    d = __import__('pandas').read_csv(FILE_1D, parse_dates=['timestamp'])
    h['ema50'] = calculate_ema(h, 50); h['ema200'] = calculate_ema(h, 200); d['atr30'] = calculate_atr(d, 30)
    row = h.iloc[-1]; atr = Decimal(str(d.iloc[-1]['atr30']))
    trend = determine_trend(row); sizing = calculate_position_sizing(); risk = evaluate_risk(price, atr, trend, sizing)
    if risk['status'] != 'PASS': raise RuntimeError(f'RISK BLOCK: {risk}')
    distance = atr * Decimal(str(ATR_MULTIPLIER))
    grid = build_grid(price, distance, GRID_LEVELS_UP, GRID_LEVELS_DOWN)
    manager = OrderManager()

    print('=' * 76)
    print('ETH-USDT ADAPTIVE GRID BOT v4.8 | DEMO LIVE')
    print('OKX DEMO ONLY / CONTROLLED GRID')
    print('=' * 76)
    print(f'Price            : {price}')
    print(f'Trend            : {trend}')
    print(f'ATR30D           : {atr}')
    print(f'Grid distance    : {distance}')
    print(f'Order size       : {sizing["order_size_usdt"]:.4f} USDT/level')
    print('Safety gate      : DEMO flag=1')
    print('Live trading     : BLOCKED')
    print('Exchange writes  : DISABLED')
    print()
    print('Grid prepared:')
    for _, g in grid.iterrows():
        qty = Decimal(str(sizing['order_size_usdt'])) / Decimal(str(g['price']))
        print(f"  {g['side']:4} L{int(g['level']):+d} @ {Decimal(str(g['price'])):.4f} qty={qty:.8f}")

    # IMPORTANT: this stage prepares and validates orders only.
    # Actual exchange submission remains disabled until a separate explicit gate is implemented.
    print()
    print(f'Orders prepared  : {len(grid)}')
    print('Orders submitted : 0')
    print('Result           : READY FOR EXPLICIT DEMO-ORDER ENABLE')

if __name__ == '__main__':
    main()
