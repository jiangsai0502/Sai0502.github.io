const $ = (id) => document.getElementById(id);

let lastStatus = null;
let lastTasks = [];

function fmt(value) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'number' && Number.isFinite(value)) return value.toFixed(1);
  return String(value);
}

function statusRow(label, value, cls = '') {
  return `<div class="row"><span class="muted">${label}</span><strong class="${cls}">${value}</strong></div>`;
}

async function tradingViewTab() {
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (active && active.id && /tradingview\.com/.test(active.url || '')) return active;
  const tabs = await chrome.tabs.query({ url: 'https://*.tradingview.com/*' });
  return tabs[0] || null;
}

async function sendToTab(message) {
  const tab = await tradingViewTab();
  if (!tab || !tab.id) {
    return { ok: false, error: '没有找到打开的 TradingView 页面' };
  }
  try {
    return await chrome.tabs.sendMessage(tab.id, message);
  } catch (err) {
    return { ok: false, error: '插件还没有注入 TradingView 页面，请刷新 TradingView 页面后再试：' + err.message };
  }
}

async function loadTasks() {
  const data = await chrome.storage.local.get({ breakevenTasks: [] });
  lastTasks = data.breakevenTasks || [];
}

async function refresh() {
  await loadTasks();
  const status = await sendToTab({ type: 'manual-be:getStatus' });
  lastStatus = status;
  render();
}

function renderStatus() {
  const s = lastStatus;
  if (!s || !s.ok) {
    $('status').innerHTML = statusRow('连接', s?.error || '未连接 TradingView', 'bad');
    return;
  }
  const auth = s.auth || {};
  $('status').innerHTML = [
    statusRow('TradingView 页面', '已连接', 'ok'),
    statusRow('Tradovate', auth.loggedIn ? '已登录' : '未检测', auth.loggedIn ? 'ok' : 'bad'),
    statusRow('环境', auth.isDemo === true ? 'Demo' : auth.isDemo === false ? 'Live' : '-'),
    statusRow('账户', s.accountId || '-'),
    statusRow('更新时间', s.updatedAt ? new Date(s.updatedAt).toLocaleTimeString() : '-')
  ].join('');
}

function renderPositions() {
  const wrap = $('positions');
  const positions = lastStatus && lastStatus.ok ? (lastStatus.positions || []) : [];
  if (!positions.length) {
    wrap.innerHTML = '<div class="empty">没有检测到当前持仓。先确认 TradingView 里 Tradovate 已登录并且有持仓。</div>';
    return;
  }

  const tpl = $('positionTemplate');
  wrap.innerHTML = '';
  for (const p of positions) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector('.symbol').textContent = p.symbol || '-';
    const dir = node.querySelector('.direction');
    dir.textContent = p.direction || '-';
    dir.classList.add(p.direction || '');
    node.querySelector('.qty').textContent = fmt(Math.abs(Number(p.qty || 0)));
    node.querySelector('.entry').textContent = fmt(p.entryPrice);
    node.querySelector('.current').textContent = fmt(p.currentPrice);
    node.querySelector('.stop').textContent = fmt(p.stopPrice);
    node.querySelector('.target').textContent = fmt(p.targetPrice);
    node.querySelector('.start').onclick = async () => {
      const triggerPrice = Number(node.querySelector('.trigger').value);
      if (!Number.isFinite(triggerPrice)) {
        alert('请输入推保触发价');
        return;
      }
      const task = {
        id: 'be-' + Date.now() + '-' + Math.random().toString(16).slice(2),
        symbol: p.symbol,
        direction: p.direction,
        triggerPrice,
        entryPrice: p.entryPrice,
        status: 'pending',
        createdAt: Date.now(),
        lastMessage: '等待触发价'
      };
      const data = await chrome.storage.local.get({ breakevenTasks: [] });
      const tasks = [task].concat(data.breakevenTasks || []).slice(0, 50);
      await chrome.storage.local.set({ breakevenTasks: tasks });
      await sendToTab({ type: 'manual-be:wake' });
      await refresh();
    };
    wrap.appendChild(node);
  }
}

async function cancelTask(id) {
  const data = await chrome.storage.local.get({ breakevenTasks: [] });
  const tasks = (data.breakevenTasks || []).map(t => t.id === id ? { ...t, status: 'cancelled', lastMessage: '已取消' } : t);
  await chrome.storage.local.set({ breakevenTasks: tasks });
  await refresh();
}

function renderTasks() {
  const wrap = $('tasks');
  if (!lastTasks.length) {
    wrap.innerHTML = '<div class="empty">暂无推保任务。</div>';
    return;
  }
  wrap.innerHTML = lastTasks.slice(0, 12).map(t => `
    <article class="card task">
      <div class="card-head">
        <strong>${t.symbol || '-'} ${t.direction || ''}</strong>
        <span class="${t.status === 'done' ? 'ok' : t.status === 'error' ? 'bad' : t.status === 'cancelled' ? 'muted' : 'warn'}">${t.status}</span>
      </div>
      <div>触发价：${fmt(t.triggerPrice)} ｜ 保本价：${fmt(t.breakevenPrice || t.entryPrice)}</div>
      <small>${t.lastMessage || ''}</small>
      ${t.status === 'pending' ? `<button data-cancel="${t.id}">取消</button>` : ''}
    </article>
  `).join('');
  wrap.querySelectorAll('[data-cancel]').forEach(btn => {
    btn.onclick = () => cancelTask(btn.dataset.cancel);
  });
}

function render() {
  renderStatus();
  renderPositions();
  renderTasks();
}

$('refresh').onclick = refresh;
chrome.storage.onChanged.addListener((changes) => {
  if (changes.breakevenTasks) refresh();
});

refresh();
setInterval(refresh, 2500);
