from decimal import Decimal
from decimal import Decimal
import pandas as pd

from eth_grid_engine_v048 import (
    FILE_1H, FILE_1D, ATR_MULTIPLIER, GRID_LEVELS_UP, GRID_LEVELS_DOWN,
    calculate_ema, calculate_atr, determine_trend, build_grid,
    calculate_position_sizing, evaluate_risk,
)

INITIAL_CAPITAL = Decimal('1000')
ORDER_SIZE = Decimal('62.50')
FEE_RATE = Decimal('0.001')


def run_backtest():
    h = pd.read_csv(FILE_1H, parse_dates=['timestamp'])
    d = pd.read_csv(FILE_1D, parse_dates=['timestamp'])
    if len(h) < 200 or len(d) < 31:
        raise RuntimeError('Insufficient historical data')

    h['ema50'] = calculate_ema(h, 50)
    h['ema200'] = calculate_ema(h, 200)
    d['atr30'] = calculate_atr(d, 30)
    sizing = calculate_position_sizing()

    cash = INITIAL_CAPITAL
    inventory = Decimal('0')
    cost_basis = Decimal('0')
    realized = Decimal('0')
    fees = Decimal('0')
    cycles = []
    equity_points = []
    active_buy = None

    for i, row in h.iterrows():
        # Indicators/grid are known only from data available before this candle.
        if i == 0:
            continue
        prev = h.iloc[i - 1]
        prior_days = d[d['timestamp'] < row['timestamp']]
        if len(prior_days) < 31:
            continue
        atr = Decimal(str(prior_days.iloc[-1]['atr30']))
        reference_price = Decimal(str(prev['close']))
        trend = determine_trend(prev)
        risk = evaluate_risk(reference_price, atr, trend, sizing)
        if risk['status'] != 'PASS':
            continue

        grid = build_grid(reference_price, atr * Decimal(str(ATR_MULTIPLIER)), GRID_LEVELS_UP, GRID_LEVELS_DOWN)
        low = Decimal(str(row['low']))
        high = Decimal(str(row['high']))
        buys = [Decimal(str(x)) for x in grid.loc[grid['side']=='BUY','price'] if low <= Decimal(str(x))]
        sells = [Decimal(str(x)) for x in grid.loc[grid['side']=='SELL','price'] if high >= Decimal(str(x))]

        # OHLC cannot establish intrabar order when both sides are touched.
        if buys and sells:
            mark = Decimal(str(row['close']))
            equity_points.append(cash + inventory * mark)
            continue

        if buys and active_buy is None:
            p = max(buys)
            qty = ORDER_SIZE / p
            fee = ORDER_SIZE * FEE_RATE
            if cash >= ORDER_SIZE + fee:
                cash -= ORDER_SIZE + fee
                inventory += qty
                cost_basis += ORDER_SIZE
                fees += fee
                active_buy = {'timestamp': row['timestamp'], 'price': p, 'qty': qty, 'buy_fee': fee}

        elif sells and active_buy is not None:
            p = min(sells)
            qty = active_buy['qty']
            gross = (p - active_buy['price']) * qty
            sell_fee = p * qty * FEE_RATE
            net = gross - active_buy['buy_fee'] - sell_fee
            cash += p * qty - sell_fee
            inventory -= qty
            cost_basis -= active_buy['price'] * qty
            realized += net
            fees += sell_fee
            cycles.append({'timestamp': row['timestamp'], 'pnl': net})
            active_buy = None

        equity_points.append(cash + inventory * Decimal(str(row['close'])))

    last_price = Decimal(str(h.iloc[-1]['close']))
    unrealized = inventory * last_price - cost_basis - (active_buy['buy_fee'] if active_buy else Decimal('0'))
    equity = cash + inventory * last_price

    peak = INITIAL_CAPITAL
    max_dd = Decimal('0')
    for value in equity_points:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)

    wins = sum(1 for c in cycles if c['pnl'] > 0)
    losses = sum(1 for c in cycles if c['pnl'] < 0)
    gross_profit = sum((c['pnl'] for c in cycles if c['pnl'] > 0), Decimal('0'))
    gross_loss = -sum((c['pnl'] for c in cycles if c['pnl'] < 0), Decimal('0'))

    return {
        'candles': len(h), 'cycles': len(cycles), 'wins': wins, 'losses': losses,
        'win_rate': Decimal(wins) / Decimal(len(cycles)) * 100 if cycles else Decimal('0'),
        'realized': realized, 'unrealized': unrealized, 'equity': equity,
        'fees': fees, 'profit_factor': gross_profit / gross_loss if gross_loss else Decimal('Infinity'),
        'avg_cycle': realized / Decimal(len(cycles)) if cycles else Decimal('0'),
        'max_drawdown': max_dd, 'inventory': inventory,
    }


def main():
    print('=' * 76)
    print('ETH-USDT ADAPTIVE GRID BOT v4.8 | BACKTEST')
    print('HISTORICAL / NO ORDERS')
    print('=' * 76)
    r = run_backtest()
    print(f"Candles          : {r['candles']}")
    print(f"Completed cycles : {r['cycles']}")
    print(f"Winning cycles   : {r['wins']}")
    print(f"Losing cycles    : {r['losses']}")
    print(f"Win rate         : {r['win_rate']:.2f}%")
    print(f"Realized P/L     : {r['realized']:.6f} USDT")
    print(f"Unrealized P/L   : {r['unrealized']:.6f} USDT")
    print(f"Equity           : {r['equity']:.6f} USDT")
    print(f"Fees             : {r['fees']:.6f} USDT")
    print(f"Profit factor    : {r['profit_factor']:.4f}")
    print(f"Avg cycle P/L    : {r['avg_cycle']:.6f} USDT")
    print(f"Max drawdown     : {r['max_drawdown']:.6f} USDT")
    print(f"ETH inventory    : {r['inventory']:.8f} ETH")
    print('Exchange writes  : NONE')

if __name__ == '__main__':
    main()
