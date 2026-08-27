import os
import time
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

from dotenv import load_dotenv
from okx import Account, MarketData, Trade

load_dotenv(Path(__file__).with_name('.env'))
FLAG = '1'
INST_ID = 'ETH-USDT'
PREFIX = 'ETHV48'
INTERVAL = 60


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


def snapshot(market, trade):
    ticker = market.get_ticker(instId=INST_ID)
    orders = trade.get_order_list(instType='SPOT', instId=INST_ID)
    if ticker.get('code') != '0':
        raise RuntimeError(f'Ticker error: {ticker}')
    if orders.get('code') != '0':
        raise RuntimeError(f'Order list error: {orders}')
    price = Decimal(ticker['data'][0]['last'])
    ours = [o for o in orders.get('data', []) if str(o.get('clOrdId', '')).startswith(PREFIX)]
    buys = sum(o.get('side') == 'buy' for o in ours)
    sells = sum(o.get('side') == 'sell' for o in ours)
    return price, ours, buys, sells


def main():
    if os.getenv('OKX_LIVE', '0') == '1':
        raise RuntimeError('LIVE GATE BLOCKED')
    market, account, trade = api_init()
    print('=' * 76)
    print('ETH-USDT ADAPTIVE GRID BOT v4.8 | DEMO MONITOR')
    print('OKX DEMO ONLY / READ ONLY / NO NEW ORDERS')
    print('=' * 76)
    print('Monitoring existing ETHV48 orders. Ctrl+C to stop.')
    while True:
        try:
            price, orders, buys, sells = snapshot(market, trade)
            ts = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
            print(f'[{ts}] ETH={price} | v4.8 open={len(orders)} | BUY={buys} SELL={sells} | writes=NONE', flush=True)
        except KeyboardInterrupt:
            print('\nMonitor stopped.')
            break
        except Exception as exc:
            print(f'MONITOR ERROR: {exc}', flush=True)
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
