from decimal import Decimal
import pandas as pd
from eth_backtest_v049 import run_backtest


def validate():
    h = pd.read_csv('eth_usdt_1h.csv', parse_dates=['timestamp'])
    d = pd.read_csv('eth_usdt_1d.csv', parse_dates=['timestamp'])
    r = run_backtest()

    checks = {
        'minimum_1h_history': len(h) >= 200,
        'minimum_1d_history': len(d) >= 31,
        'no_negative_drawdown': r['max_drawdown'] >= 0,
        'equity_consistent': abs(r['equity'] - (r['cash'] + r['inventory'] * r['mark_price'])) < Decimal('0.00001'),
        'fees_positive_or_zero': r['fees'] >= 0,
        'inventory_nonnegative': r['inventory'] >= 0,
        'cycles_consistent': r['cycles'] == r['wins'] + r['losses'],
    }
    print('=' * 76)
    print('ETH-USDT v4.9 | BACKTEST VALIDATION')
    print('READ ONLY / NO ORDERS')
    print('=' * 76)
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL':5} | {name}")
    print('-' * 76)
    print(f"Realized P/L     : {r['realized']:.6f} USDT")
    print(f"Unrealized P/L   : {r['unrealized']:.6f} USDT")
    print(f"Equity           : {r['equity']:.6f} USDT")
    print(f"Max drawdown     : {r['max_drawdown']:.6f} USDT")
    print(f"Cash             : {r['cash']:.6f} USDT")
    print(f"Mark price       : {r['mark_price']:.2f} USDT")
    print(f"ETH inventory    : {r['inventory']:.8f} ETH")
    print(f"Cycles           : {r['cycles']}")
    print(f"Validation       : {'PASS' if all(checks.values()) else 'FAIL'}")

if __name__ == '__main__':
    validate()
