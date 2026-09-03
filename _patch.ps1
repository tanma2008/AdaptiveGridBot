$p='D:\AdaptiveGridBot\adaptive_grid_dashboard.py'
$s=Get-Content -Raw -LiteralPath $p
$s=$s.Replace('from flask import Flask, render_template_string, jsonify','from flask import Flask, render_template_string, jsonify, request')
$s=$s.Replace('def get_dashboard():','def get_dashboard(hours=24):')
$s=$s.Replace('period_fills(fetch_fills(api_for(a), a.get("symbol", SYMBOL)), 24)','period_fills(fetch_fills(api_for(a), a.get("symbol", SYMBOL)), hours)')
$s=$s.Replace('<div class="sub">🤖 9 BOT · 🌐 3 MARKETS · 🧪 DEMO · ⏱️ 24H · 🔒 READ ONLY</div>','<div class="sub">🤖 9 BOT · 🌐 3 MARKETS · 🧪 DEMO · <span id="periodLabel">⏱️ 24H</span> · 🔒 READ ONLY</div>')
$s=$s.Replace('.btn{background:#25304a;','.periods{display:flex;gap:8px;margin:0 0 14px}.period{background:#25304a;color:#dce4f5;border:1px solid #34415e;border-radius:9px;padding:8px 16px;cursor:pointer;font-weight:700}.period.active{background:#3a4d78;color:#fff;box-shadow:0 0 0 1px #667ba8}.btn{background:#25304a;')
$s=$s.Replace('<div class="matrix-wrap">','<div class="periods"><button class="period active" data-period="24h" onclick="setPeriod(''24h'')">24H</button><button class="period" data-period="3d" onclick="setPeriod(''3d'')">3D</button><button class="period" data-period="7d" onclick="setPeriod(''7d'')">7D</button><button class="period" data-period="30d" onclick="setPeriod(''30d'')">30D</button></div>\n<div class="matrix-wrap">')
$s=$s.Replace('async function load(){\n const r=await fetch("/api/dashboard");','let currentPeriod=new URLSearchParams(location.search).get("period")||"24h";\nconst periodHours={"24h":24,"3d":72,"7d":168,"30d":720};\nfunction setPeriod(p){currentPeriod=p;history.replaceState(null,"",`/?period=${p}`);updatePeriodUI();load()}\nfunction updatePeriodUI(){document.querySelectorAll(".period").forEach(b=>b.classList.toggle("active",b.dataset.period===currentPeriod));document.getElementById("periodLabel").textContent="⏱️ "+currentPeriod.toUpperCase()}\nasync function load(){\n updatePeriodUI();\n const r=await fetch(`/api/dashboard?period=${currentPeriod}`);')
$s=$s.Replace('@app.route("/api/dashboard")\ndef api_dashboard():\n    return jsonify(get_dashboard())','@app.route("/api/dashboard")\ndef api_dashboard():\n    period = request.args.get("period", "24h").lower()\n    hours = {"24h": 24, "3d": 72, "7d": 168, "30d": 720}.get(period, 24)\n    return jsonify(get_dashboard(hours))')
Set-Content -LiteralPath $p -Value $s -Encoding utf8
python -m py_compile $p
if($LASTEXITCODE -eq 0){Copy-Item -LiteralPath $p -Destination $p.Replace('_patch.ps1','adaptive_grid_dashboard.py') -Force}
