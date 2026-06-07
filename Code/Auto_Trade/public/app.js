let last = null;

const fields = [
  ['enabled', '自动交易', 'checkbox'],
  ['contract', '合约', 'text'],
  ['qty', '手数', 'number'],
  ['maxSameDirectionTrades', '最大同向单数', 'number'],
  ['dailyLossLimit', '日亏损限制', 'number'],
  ['dailyProfitLimit', '日盈利停止', 'number'],
  ['maxConsecutiveLosses', '连续亏损停止', 'number']
];

function $(id) { return document.getElementById(id); }

function render(data) {
  last = data;
  const s = data.config.strategy;
  const risk = data.state.risk;
  $('clock').textContent = `北京 ${data.time.beijing.date} ${String(data.time.beijing.hour).padStart(2, '0')}:${String(data.time.beijing.minute).padStart(2, '0')}`;
  $('status').innerHTML = `
    <div class="row"><label>自动交易</label><strong class="${s.enabled ? 'ok' : 'bad'}">${s.enabled ? 'ON' : 'OFF'}</strong></div>
    <div class="row"><label>禁开时段</label><strong class="${data.time.blocked ? 'bad' : 'ok'}">${data.time.blocked ? '04-07 BLOCKED' : '允许'}</strong></div>
    <div class="row"><label>扩展在线</label><strong class="${data.state.extension?.lastSeenAt ? 'ok' : 'bad'}">${data.state.extension?.lastSeenAt || '未连接'}</strong></div>
    <div class="row"><label>Tradovate</label><strong>${data.state.extension?.auth?.loggedIn ? '已登录' : '未检测'}</strong></div>
    <div class="row"><label>Bracket 模板</label><strong class="${data.state.extension?.templateReady ? 'ok' : 'bad'}">${data.state.extension?.templateReady ? '已捕获' : '未捕获'}</strong></div>
    <div class="row"><label>已消费波段</label><strong>${data.state.extension?.consumedWaves || 0}</strong></div>
    <div class="row"><label>任务队列</label><strong>${(data.state.tasks || []).filter(t => t.status === 'pending' || t.status === 'dispatched').length}</strong></div>
    <div class="row"><label>日 PnL</label><strong class="${risk.dailyPnl >= 0 ? 'ok' : 'bad'}">${risk.dailyPnl}</strong></div>
    <div class="row"><label>连续亏损</label><strong>${risk.consecutiveLosses}</strong></div>
    <div class="row"><label>暂停原因</label><strong>${risk.pausedReason || '-'}</strong></div>
  `;
  $('settings').innerHTML = fields.map(([key, label, type]) => `
    <div class="row">
      <label for="${key}">${label}</label>
      <input id="${key}" type="${type}" ${type === 'checkbox' ? (s[key] ? 'checked' : '') : `value="${s[key]}"`}>
    </div>
  `).join('');
  $('events').innerHTML = data.state.events.slice(0, 20).map(e => `
    <div class="event">
      <small>${e.at} · ${e.level || 'info'}</small>
      <div>${e.message || ''}</div>
      ${e.signal ? `<pre>${JSON.stringify(e.signal, null, 2)}</pre>` : ''}
      ${e.report ? `<pre>${JSON.stringify(e.report, null, 2)}</pre>` : ''}
    </div>
  `).join('');
}

async function refresh() {
  const res = await fetch('/api/status');
  render(await res.json());
}

async function post(url, body = {}) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const json = await res.json();
  await refresh();
  return json;
}

$('save').onclick = async () => {
  const strategy = {};
  for (const [key, , type] of fields) {
    const el = $(key);
    strategy[key] = type === 'checkbox' ? el.checked : (type === 'number' ? Number(el.value) : el.value);
  }
  await post('/api/config', { strategy });
};

$('testAuth').onclick = async () => {
  await refresh();
};

$('flatten').onclick = async () => {
  if (!confirm('确认全平并撤所有挂单？')) return;
  const r = await post('/api/flatten');
  if (!r.ok) alert(r.error);
};

refresh();
setInterval(refresh, 3000);
