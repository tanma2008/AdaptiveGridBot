#!/usr/bin/env python3
"""
Adaptive Grid Bot - Read-only Web Dashboard
Designed for the existing Linux server running v5.1.1.

- No OKX order placement/cancellation.
- Reads the same .env files used by the report.
- Shows A/B/C 12H performance.
- C is v5.1.1 / .env.v50 / V511.
- Auto-refreshes every 30 seconds.
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from flask import Flask, render_template_string, jsonify

import okx.Trade as Trade
from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
SYMBOL = "BTC-USDT"

ACCOUNTS = [
    {"key": "A", "name": "v4.8", "env": ".env", "prefix": "v048", "symbol": "BTC-USDT"},
    {"key": "B", "name": "v4.9", "env": ".env.v49", "prefix": "v049", "symbol": "BTC-USDT"},
    {"key": "C", "name": "v5.1.1", "env": ".env.v50", "prefix": "V511", "symbol": "BTC-USDT"},
    {"key": "D", "name": "ETH v4.8", "env": ".env", "prefix": "ETHv048", "symbol": "ETH-USDT"},
    {"key": "E", "name": "ETH v4.9", "env": ".env.v49", "prefix": "ETHv049", "symbol": "ETH-USDT"},
    {"key": "F", "name": "ETH v5.1.1", "env": ".env.v50", "prefix": "F511", "symbol": "ETH-USDT"},
    {"key": "G", "name": "SOL v4.8", "env": ".env", "prefix": "", "symbol": "SOL-USDT", "all_symbol_orders": True},
    {"key": "H", "name": "SOL v4.9", "env": ".env.v49", "prefix": "", "symbol": "SOL-USDT", "all_symbol_orders": True},
    {"key": "I", "name": "SOL v5.1.1", "env": ".env.v50", "prefix": "", "symbol": "SOL-USDT", "all_symbol_orders": True},
]

app = Flask(__name__)
D = Decimal

@app.after_request
def add_no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response



def api_for(account):
    load_dotenv(os.path.join(BASE, account["env"]), override=True)
    return Trade.TradeAPI(
        api_key=os.getenv("OKX_API_KEY"),
        api_secret_key=os.getenv("OKX_SECRET_KEY"),
        passphrase=os.getenv("OKX_PASSPHRASE"),
        flag=os.getenv("OKX_FLAG", "1"),
        debug=False,
        domain="https://www.okx.com",
    )


def fetch_fills(api, symbol):
    result = []
    after = None
    for _ in range(10):
        kw = {"instType": "SPOT", "instId": symbol, "limit": "100"}
        if after:
            kw["after"] = after
        r = api.get_fills(**kw)
        if r.get("code") != "0":
            raise RuntimeError(str(r))
        rows = r.get("data", [])
        if not rows:
            break
        result.extend(rows)
        if len(rows) < 100:
            break
        last = rows[-1].get("billId")
        if not last or last == after:
            break
        after = last
    return result


def period_fills(rows, hours):
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    out = []
    for f in rows:
        try:
            t = datetime.fromtimestamp(int(f["ts"]) / 1000, timezone.utc)
            if start <= t <= end:
                out.append(f)
        except Exception:
            pass
    return out


def report(rows):
    inventory = []
    cycles = []
    cycle_id = 0

    for f in sorted(rows, key=lambda x: int(x.get("ts", 0))):
        side = f.get("side", "").lower()
        px = D(str(f.get("fillPx", "0")))
        sz = D(str(f.get("fillSz", "0")))
        fee = abs(D(str(f.get("fee", "0"))))
        if px <= 0 or sz <= 0:
            continue

        if side == "buy":
            inventory.append({"px": px, "sz": sz, "fee": fee})
        elif side == "sell":
            rem = sz
            while rem > 0 and inventory:
                b = inventory[0]
                m = min(rem, b["sz"])
                bf = b["fee"] * m / b["sz"] if b["sz"] else D("0")
                sf = fee * m / sz if sz else D("0")
                pnl = px*m - b["px"]*m - bf - sf
                cycle_id += 1
                cycles.append(pnl)
                b["sz"] -= m
                rem -= m
                if b["sz"] <= 0:
                    inventory.pop(0)

    wins = [x for x in cycles if x > 0]
    losses = [x for x in cycles if x < 0]
    realized = sum(cycles, D("0"))
    gross_profit = sum(wins, D("0"))
    gross_loss = abs(sum(losses, D("0")))
    pf = (gross_profit / gross_loss) if gross_loss else None

    return {
        "fills": len(rows),
        "cycles": len(cycles),
        "win_rate": float(D(len(wins))/D(len(cycles))*100) if cycles else None,
        "pnl": float(realized),
        "pf": float(pf) if pf is not None else None,
        "avg": float(realized/D(len(cycles))) if cycles else None,
        "best": float(max(cycles)) if cycles else None,
        "worst": float(min(cycles)) if cycles else None,
        "inventory": float(sum((x["sz"] for x in inventory), D("0"))),
        "has_data": bool(rows),
    }


def get_open_orders(account):
    try:
        api = api_for(account)
        symbol = account.get("symbol", SYMBOL)
        r = api.get_order_list(instType="SPOT")
        if r.get("code") != "0":
            return {"all": 0, "bot": 0, "buy": 0, "sell": 0}
        rows = [x for x in r.get("data", []) if x.get("instId") == symbol]
        bot = rows if account.get("all_symbol_orders") else [x for x in rows if str(x.get("clOrdId", "")).startswith(account["prefix"])]
        return {"all": len(rows), "bot": len(bot), "buy": sum(x.get("side") == "buy" for x in bot), "sell": sum(x.get("side") == "sell" for x in bot)}
    except Exception:
        return {"all": 0, "bot": 0, "buy": 0, "sell": 0}


def get_dashboard():
    data = []
    for a in ACCOUNTS:
        try:
            rows = period_fills(fetch_fills(api_for(a), a.get("symbol", SYMBOL)), 24)
            r = report(rows)
            orders = get_open_orders(a)
            r["has_data"] = bool(rows or orders["bot"])
            data.append({**a, **r, "orders": orders, "error": None})
        except Exception as e:
            data.append({**a, "fills": 0, "cycles": 0, "win_rate": None,
                         "pnl": None, "pf": None, "avg": None, "best": None,
                         "worst": None, "inventory": None, "has_data": False,
                         "orders": {"all": 0, "bot": 0, "buy": 0, "sell": 0},
                         "error": str(e)})
    return data


HTML = r"""
<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Adaptive Grid Bot Dashboard</title>
<style>
body{margin:0;background:#0b1020;color:#e8edf7;font-family:Arial,sans-serif}
.wrap{max-width:1200px;margin:auto;padding:24px}
h1{margin:0 0 6px}.sub{color:#9aa6bd;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.card{background:#151c2f;border:1px solid #29344e;border-radius:14px;padding:18px}
.card h2{margin-top:0}.big{font-size:30px;font-weight:700}
.ok{color:#48d597}.muted{color:#9aa6bd}.warn{color:#ffca62}
table{width:100%;border-collapse:collapse;margin-top:18px;background:#151c2f;border-radius:14px;overflow:hidden}
th,td{padding:12px;border-bottom:1px solid #29344e;text-align:right}th:first-child,td:first-child{text-align:left}
.btn{background:#25304a;color:#fff;border:0;border-radius:8px;padding:9px 14px;cursor:pointer}
.status{display:inline-block;padding:4px 8px;border-radius:99px;background:#173a31;color:#6de4b0}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
<h1>ADAPTIVE GRID BOT DASHBOARD</h1>
<div class="sub">9 BOT · BTC/ETH/SOL · DEMO · 24H · Read Only · BTC/ETH/SOL · DEMO · 24H · Read Only</div>
<div class="grid" id="cards"></div>
<table>
<thead><tr id="head"><th>Metric</th></tr></thead>
<tbody id="tbl"></tbody>
</table>
<p class="muted">Auto refresh: 30s ยท Last update: <span id="time">-</span></p>
<button class="btn" onclick="load()">Refresh now</button>
</div>
<script>
const names=["A","B","C","D","E","F","G","H","I"];
function n(v,d=4){return v===null||v===undefined?"N/A":Number(v).toFixed(d)}
function pct(v){return v===null||v===undefined?"N/A":Number(v).toFixed(2)+"%"}
function pnl(v){return v===null||v===undefined?"N/A":(v>=0?"+":"")+Number(v).toFixed(6)}
async function load(){
 const r=await fetch("/api/dashboard"); const a=await r.json();
 document.getElementById("cards").innerHTML=a.map(x=>`
 <div class="card"><h2>${x.key} / ${x.name}</h2>
 <div class="big">${pnl(x.pnl===null?0:x.pnl)}</div>
 <div class="muted">Realized P/L · 24H</div><br>
 <span class="status">DEMO</span>
 ${x.error?`<p class="warn">${x.error}</p>`:""}
 </div>`).join("");
 const metrics=[["Fills",x=>x.fills],["Completed cycles",x=>x.cycles],["Win rate",x=>pct(x.win_rate)],["Realized P/L",x=>pnl(x.pnl)],["Profit factor",x=>n(x.pf,4)],["Avg cycle P/L",x=>pnl(x.avg)],["Best cycle",x=>pnl(x.best)],["Worst cycle",x=>pnl(x.worst)],["Unmatched inventory",x=>n(x.inventory,8)],["Active orders",x=>x.orders.bot],["BUY / SELL",x=>`${x.orders.buy} / ${x.orders.sell}`]];
 document.getElementById("head").innerHTML="<th>Metric</th>"+a.map(x=>`<th>${x.key} / ${x.symbol.replace("-USDT","")} ${x.name}</th>`).join("");
 document.getElementById("tbl").innerHTML=metrics.map(m=>`<tr><td>${m[0]}</td>${a.map(x=>`<td>${m[1](x)}</td>`).join("")}</tr>`).join("");
 document.getElementById("time").textContent=new Date().toLocaleString();
}
load();setInterval(load,30000);
</script>
</body></html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(get_dashboard())

if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

