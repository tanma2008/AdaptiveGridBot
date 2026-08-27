import os
from pathlib import Path
from decimal import Decimal
from dotenv import load_dotenv
from okx import Account, MarketData, Trade

load_dotenv(Path(__file__).with_name('.env'))
INST_ID = 'ETH-USDT'
FLAG = '1'
ORDER_USDT = Decimal('10')


def env(name):
    v = os.getenv(name)
    if not v: raise RuntimeError(f'Missing environment variable: {name}')
    return v


def main():
    if os.getenv('OKX_LIVE', '0') == '1':
        raise RuntimeError('LIVE GATE BLOCKED')
    api_key, secret, passphrase = env('OKX_API_KEY'), env('OKX_SECRET_KEY'), env('OKX_PASSPHRASE')
    market = MarketData.MarketAPI(api_key, secret, passphrase, False, FLAG)
    account = Account.AccountAPI(api_key, secret, passphrase, False, FLAG)
    trade = Trade.TradeAPI(api_key, secret, passphrase, False, FLAG)

    ticker = market.get_ticker(instId=INST_ID)
    if ticker.get('code') != '0': raise RuntimeError(f'Ticker failed: {ticker}')
    px = Decimal(ticker['data'][0]['last'])
    print('=' * 76)
    print('ETH-USDT v4.8 | OKX DEMO ORDER TEST')
    print('DEMO ONLY / MANUAL TEST')
    print('=' * 76)
    print(f'Last price       : {px}')
    print(f'Test notional    : {ORDER_USDT} USDT')
    print('Order submission : DISABLED')
    print('Exchange writes  : NONE')
    print('Live trading     : BLOCKED')
    print('Next step        : enable exactly one controlled DEMO order only after approval')

if __name__ == '__main__': main()
