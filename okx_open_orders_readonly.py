import os
from dotenv import load_dotenv
from okx.api import Trade

load_dotenv('.env.v49', override=True)
flag = os.getenv('OKX_FLAG', '1')
api_key = os.getenv('OKX_API_KEY')
secret = os.getenv('OKX_SECRET_KEY')
passphrase = os.getenv('OKX_PASSPHRASE')
if not all((api_key, secret, passphrase)):
    raise SystemExit('Missing OKX credentials in .env.v49')
api = Trade(api_key, secret, passphrase, False, flag)
result = api.get_order_list(instType='SPOT', instId='', limit='100')
if result.get('code') != '0':
    raise SystemExit('OKX API error: ' + str(result.get('msg', 'unknown')))
targets = {'BTC-USDT', 'ETH-USDT', 'SOL-USDT'}
rows = [x for x in result.get('data', []) if x.get('instId') in targets]
print('=' * 92)
print('OKX OPEN ORDERS - READ ONLY - BTC / ETH / SOL')
print(f'FLAG: {flag} | TOTAL TARGET ORDERS: {len(rows)}')
print('=' * 92)
if not rows:
    print('NO OPEN ORDERS for BTC-USDT / ETH-USDT / SOL-USDT')
else:
    for x in sorted(rows, key=lambda z: (z.get('instId',''), z.get('side',''), z.get('px',''))):
        print(f"{x.get('instId',''):9} {x.get('side','').upper():4} px={x.get('px',''):>14} sz={x.get('sz',''):>14} filled={x.get('accFillSz',''):>14} state={x.get('state',''):>18} ordId={x.get('ordId','')}")
    print('-' * 92)
    for symbol in sorted(targets):
        s = [x for x in rows if x.get('instId') == symbol]
        print(f"{symbol}: {len(s)} orders | BUY={sum(x.get('side') == 'buy' for x in s)} | SELL={sum(x.get('side') == 'sell' for x in s)}")
print('READ ONLY: no place/cancel/amend operations are called.')
