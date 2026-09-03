from pathlib import Path
p=Path(r'D:\AdaptiveGridBot\adaptive_grid_dashboard.py')
s=p.read_text(encoding='utf-8')
s=s.replace('from flask import Flask, render_template_string, jsonify','from flask import Flask, render_template_string, jsonify, request')
s=s.replace('def get_dashboard():','def get_dashboard(hours=24):')
s=s.replace('period_fills(fetch_fills(api_for(a), a.get("symbol", SYMBOL)), 24)','period_fills(fetch_fills(api_for(a), a.get("symbol", SYMBOL)), hours)')
s=s.replace('<div class="sub">🤖 9 BOT · 🌐 3 MARKETS · 🧪 DEMO · ⏱️ 24H · 🔒 READ ONLY</div>','<div class="sub">🤖 9 BOT · 🌐 3 MARKETS · 🧪 DEMO · <span id="periodLabel">⏱️ 24H</span> · 🔒 READ ONLY</div>')
s=s.replace('.btn{background:#25304a;','.periods{display:flex;gap:8px;margin:0 0 14px}.period{background:#25304a;color:#dce4f5;border:1px solid #34415e;border-radius:9px;padding:8px 16px;cursor:pointer;font-weight:700}.period.active{background:#3a4d78;color:#fff;box-shadow:0 0 0 1px #667ba8}.btn{background:#25304a;')
periods='''<div class="periods"><button class="period active" data-period="24h" onclick="setPeriod('24h')">24H</button><button class="period" data-period="3d" onclick="setPeriod('3d')">3D</button><button class="period" data-period="7d" onclick="setPeriod('7d')">7D</button><button class="period" data-period="30d" onclick="setPeriod('30d')">30D</button></div>'''
s=s.replace('<div class="matrix-wrap">',periods+'\n<div class="matrix-wrap">')
old='''async function load(){
 const r=await fetch("/api/dashboard");'''
new='''let currentPeriod=new URLSearchParams(location.search).get("period")||"24h";
function setPeriod(p){currentPeriod=p;history.replaceState(null,"",`/?period=${p}`);updatePeriodUI();load()}
function updatePeriodUI(){document.querySelectorAll(".period").forEach(b=>b.classList.toggle("active",b.dataset.period===currentPeriod));document.getElementById("periodLabel").textContent="⏱️ "+currentPeriod.toUpperCase()}
async function load(){
 updatePeriodUI();
 const r=await fetch(`/api/dashboard?period=${currentPeriod}`);'''
s=s.replace(old,new)
old_api='''@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(get_dashboard())'''
new_api='''@app.route("/api/dashboard")
def api_dashboard():
    period = request.args.get("period", "24h").lower()
    hours = {"24h": 24, "3d": 72, "7d": 168, "30d": 720}.get(period, 24)
    return jsonify(get_dashboard(hours))'''
s=s.replace(old_api,new_api)
p.write_text(s,encoding='utf-8')
print('patched', p)
