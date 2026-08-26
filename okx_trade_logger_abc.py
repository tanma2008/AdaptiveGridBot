# OKX DEMO TRADE CSV LOGGER A / B / C
# READ ONLY - NO ORDERS

import os
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import okx.Trade as Trade


ACCOUNTS = [
    ("A", "v4.8", ".env", "okx_trades_A_v048.csv"),
    ("B", "v4.9", ".env.v49", "okx_trades_B_v049.csv"),
    ("C", "v5.1.1", ".env.v50", "okx_trades_C_v511.csv"),
]

SYMBOL = "BTC-USDT"
INTERVAL = 30

FIELDS = [
    "account", "bot", "ts", "datetime_utc",
    "tradeId", "billId", "ordId", "clOrdId",
    "side", "fillPx", "fillSz", "fillPnl",
    "fee", "feeCcy", "execType", "source"
]


def make_api(env_file):
    load_dotenv(env_file, override=True)

    api_key = os.getenv("OKX_API_KEY")
    secret = os.getenv("OKX_SECRET_KEY")
    passphrase = os.getenv("OKX_PASSPHRASE")
    flag = os.getenv("OKX_FLAG", "1")

    if not api_key or not secret or not passphrase:
        raise RuntimeError(f"Missing API credentials: {env_file}")

    return Trade.TradeAPI(
        api_key,
        secret,
        passphrase,
        False,
        flag,
    )


def load_existing(path):
    if not path.exists():
        return set()

    seen = set()

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (
                row.get("tradeId")
                or row.get("billId")
                or (
                    f"{row.get('ordId')}:"
                    f"{row.get('ts')}:"
                    f"{row.get('fillPx')}:"
                    f"{row.get('fillSz')}"
                )
            )
            seen.add(key)

    return seen


def append_rows(path, rows):
    exists = path.exists()

    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=FIELDS,
            extrasaction="ignore",
        )

        if not exists:
            writer.writeheader()

        writer.writerows(rows)


def fetch_fills(api):
    result = api.get_fills(
        instType="SPOT",
        instId=SYMBOL,
        limit="100",
    )

    if result.get("code") != "0":
        raise RuntimeError(result)

    return result.get("data", [])


def main():
    print("=" * 72)
    print("       OKX DEMO TRADE CSV LOGGER A / B / C")
    print("=" * 72)
    print("READ ONLY - NO ORDERS")
    print(f"Symbol   : {SYMBOL}")
    print(f"Interval : {INTERVAL}s")
    print()

    seen = {}

    for account, bot, env, filename in ACCOUNTS:
        seen[account] = load_existing(Path(filename))
        print(
            f"{account} / {bot}: "
            f"{len(seen[account])} existing records"
        )

    print()
    print("LOGGER ACTIVE")
    print("Ctrl+C = STOP")
    print()

    while True:
        for account, bot, env, filename in ACCOUNTS:
            try:
                api = make_api(env)
                fills = fetch_fills(api)

                new_rows = []

                for x in reversed(fills):
                    key = (
                        str(x.get("tradeId") or "")
                        or str(x.get("billId") or "")
                        or (
                            f"{x.get('ordId')}:"
                            f"{x.get('ts')}:"
                            f"{x.get('fillPx')}:"
                            f"{x.get('fillSz')}"
                        )
                    )

                    if key in seen[account]:
                        continue

                    ts = x.get("ts", "")

                    try:
                        dt = datetime.fromtimestamp(
                            int(ts) / 1000,
                            tz=timezone.utc,
                        ).isoformat()
                    except Exception:
                        dt = ""

                    new_rows.append({
                        "account": account,
                        "bot": bot,
                        "ts": ts,
                        "datetime_utc": dt,
                        "tradeId": x.get("tradeId", ""),
                        "billId": x.get("billId", ""),
                        "ordId": x.get("ordId", ""),
                        "clOrdId": x.get("clOrdId", ""),
                        "side": x.get("side", ""),
                        "fillPx": x.get("fillPx", ""),
                        "fillSz": x.get("fillSz", ""),
                        "fillPnl": x.get("fillPnl", ""),
                        "fee": x.get("fee", ""),
                        "feeCcy": x.get("feeCcy", ""),
                        "execType": x.get("execType", ""),
                        "source": "OKX_DEMO",
                    })

                    seen[account].add(key)

                if new_rows:
                    append_rows(
                        Path(filename),
                        new_rows,
                    )

                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] "
                        f"{account} / {bot}: "
                        f"+{len(new_rows)} fills -> {filename}"
                    )

            except Exception as e:
                print(
                    f"[LOGGER ERROR] "
                    f"{account} / {bot}: {e}"
                )

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
