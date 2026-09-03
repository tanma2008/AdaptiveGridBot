from pathlib import Path
p=Path(r"D:\AdaptiveGridBot\adaptive_grid_dashboard.py")
s=p.read_text(encoding="utf-8")
s=s.replace('from flask import Flask, render_template_string, jsonify','from flask import Flask, render_template_string, jsonify, request')
s=s.replace('def period_fills(rows, hours):\n    end = datetime.now(timezone.utc)\n    start = end - timedelta(hours=hours)\n    out = []\n    for f in rows:\n        try:\n            t = datetime.fromtimestamp(int(f["ts"]) / 1000, timezone.utc)\n            if start <= t <= end:\n                out.append(f)\n        except Exception:\n            pass\n    return out', '''def period_fills(rows, period):
    end = datetime.now(timezone.utc)
    if period == "24h": start = end - timedelta(hours=24)
    elif period == "3d": start = end - timedelta(days=3)
    elif period == "7d": start = end - timedelta(days=7)
    elif period == "30d": start = end - timedelta(days=30)
    else: start = end - timedelta(hours=24)
    out = []
    for f in rows:
        try:
            t = datetime.fromtimestamp(int(f["ts"]) / 1000, timezone.utc)
            if start <= t <= end: out.append(f)
        except Exception: pass
    return out''')
s=s.replace('def get_dashboard():\n    data = []\n    for a in ACCOUNTS:\n        try:\n            rows = period_fills(fetch_fills(api_for(a), a.get("symbol", SYMBOL)), 24)', 'def get_dashboard(period="24h"):\n    data = []\n    for a in ACCOUNTS:\n        try:\n            rows = period_fills(fetch_fills(api_for(a), a.get("symbol", SYMBOL)), period)')
s=s.replace('<div class="sub">🤖 9 BOT · 🌐 3 MARKETS · 🧪 DEMO · ⏱️ 24H · 🔒 READ ONLY</div>\n<div class="matrix-wrap">', '<div class="sub">🤖 9 BOT · 🌐 3 MARKETS · 🧪 DEMO · <span id="periodLabel">⏱️ 24H</span> · 🔒 READ ONLY</div>\n<div class="periods"><button class="btn period active" data-period="24h" onclick="setPeriod(\'24h\')">24H</button><button class="btn period" data-period="3d" onclick="setPeriod(\'3d\')">3D</button><button class="btn period" data-period="7d" onclick="setPeriod(\'7d\')">7D</button><button class="btn period" data-period="30d" onclick="setPeriod(\'30d\')">30D</button></div>\n<div class="matrix-wrap">')
s=s.replace('.btn{background:#25304a;color:#fff;border:0;border-radius:8px;padding:9px 14px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.2)}', '.btn{background:#25304a;color:#fff;border:0;border-radius:8px;padding:9px 14px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.2)} .periods{display:flex;gap:8px;margin:0 0 14px}.period.active{background:#48d597;color:#07130f;font-weight:800}')
s=s.replace('async function load(){\n const r=await fetch("/api/dashboard"); const a=await r.json();', 'let currentPeriod="24h";\nfunction setPeriod(p){currentPeriod=p;document.querySelectorAll(".period").forEach(b=>b.classList.toggle("active",b.dataset.period===p));document.getElementById("periodLabel").textContent="⏱️ "+p.toUpperCase();load()}\nasync function load(){\n const r=await fetch("/api/dashboard?period="+encodeURIComponent(currentPeriod)); const a=await r.json();')
s=s.replace('@app.route("/api/dashboard")\ndef api_dashboard():\n    return jsonify(get_dashboard())', '@app.route("/api/dashboard")\ndef api_dashboard():\n    period=request.args.get("period","24h").lower()\n    if period not in {"24h","3d","7d","30d"}: period="24h"\n    return jsonify(get_dashboard(period))')
p.write_text(s,encoding="utf-8")
print("updated",len(s.splitlines()))# execute this helper with: python D:\AdaptiveGridBot\_edit_dashboard.py
