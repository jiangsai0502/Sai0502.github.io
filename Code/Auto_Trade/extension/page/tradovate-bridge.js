(function() {
  'use strict';

  if (window.__mssTradovateBridgeLoaded) return;
  window.__mssTradovateBridgeLoaded = true;

  const LOG = '[MSS-Bridge]';
  const COPY_TAG = 'mssauto';
  let auth = { jwt: null, baseUrl: null, isDemo: null, capturedAt: null };
  let accounts = null;
  const liveState = {};
  let orderTemplate = loadTemplate();
  let waveLedger = loadWaveLedger();

  function log() {
    try { console.log.apply(console, [LOG].concat([].slice.call(arguments))); } catch {}
  }

  function loadTemplate() {
    try {
      const raw = localStorage.getItem('mssAutoOrderTemplate');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function saveTemplate(template) {
    orderTemplate = template;
    try { localStorage.setItem('mssAutoOrderTemplate', JSON.stringify(template)); } catch {}
  }

  function loadWaveLedger() {
    try {
      const raw = localStorage.getItem('mssAutoWaveLedger');
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveWaveLedger() {
    try { localStorage.setItem('mssAutoWaveLedger', JSON.stringify(waveLedger)); } catch {}
  }

  function waveKey(signal) {
    return signal.waveId || (signal.direction + ':' + (signal.waveStartBar || signal.waveStart));
  }

  function markWaveConsumed(signal, detail) {
    const key = waveKey(signal);
    waveLedger[key] = {
      status: 'consumed',
      consumedAt: Date.now(),
      direction: signal.direction,
      waveStartBar: signal.waveStartBar,
      waveStart: signal.waveStart,
      detail: detail || null
    };
    saveWaveLedger();
    return key;
  }

  function markWaveWorking(signal, detail) {
    const key = waveKey(signal);
    waveLedger[key] = {
      status: 'working',
      workingAt: Date.now(),
      direction: signal.direction,
      waveStartBar: signal.waveStartBar,
      waveStart: signal.waveStart,
      detail: detail || null
    };
    saveWaveLedger();
    return key;
  }

  function normalizeHeaders(h) {
    const out = {};
    try {
      if (h instanceof Headers) {
        for (const [k, v] of h.entries()) out[k.toLowerCase()] = v;
        return out;
      }
    } catch {}
    if (h && typeof h === 'object') {
      Object.keys(h).forEach(k => { out[k.toLowerCase()] = String(h[k]); });
    }
    return out;
  }

  function parseBody(body) {
    if (!body) return {};
    if (typeof body === 'string') {
      try { return JSON.parse(body); } catch {}
      const params = new URLSearchParams(body);
      const out = {};
      for (const [k, v] of params.entries()) out[k] = v;
      return out;
    }
    if (body instanceof URLSearchParams) {
      const out = {};
      for (const [k, v] of body.entries()) out[k] = v;
      return out;
    }
    return {};
  }

  function encodeBody(obj) {
    const params = new URLSearchParams();
    Object.keys(obj).forEach(k => {
      if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') params.append(k, String(obj[k]));
    });
    return params.toString();
  }

  function captureAuth(url, headers) {
    if (!String(url).includes('tradovateapi.com')) return;
    const raw = headers.authorization;
    if (!raw) return;
    const m = raw.match(/^Bearer\s+(.+)$/i);
    if (!m) return;
    const base = String(url).match(/^(https?:\/\/[^/]+)/)?.[1];
    auth = {
      jwt: m[1],
      baseUrl: base,
      isDemo: !!base && base.includes('demo'),
      capturedAt: Date.now()
    };
  }

  function maybeCaptureOrderTemplate(url, method, parsedBody) {
    if (method !== 'POST') return;
    if (!/\/accounts\/[^/?]+\/orders(\?|$)/.test(String(url))) return;
    if (/requestId=(tdvcopy|tdvpopup|mssauto)/.test(String(url))) return;
    const keys = Object.keys(parsedBody || {});
    const hasEntry = keys.some(k => /price|limit/i.test(k));
    const hasStop = keys.some(k => /stop|loss|sl/i.test(k));
    const hasProfit = keys.some(k => /profit|take|tp|target/i.test(k));
    if (hasEntry && hasStop && hasProfit) {
      saveTemplate({ capturedAt: Date.now(), body: parsedBody });
      log('captured bracket order template', parsedBody);
    }
  }

  function updateCache(url, method, data) {
    if (!data || !data.d) return;
    if (/\/accounts(\?|$)/.test(url) && method === 'GET') {
      accounts = data.d;
      return;
    }
    const m = String(url).match(/\/accounts\/([^/?]+)\/(state|positions|orders|executions)/);
    if (m && method === 'GET') {
      liveState[m[1]] ||= {};
      liveState[m[1]][m[2]] = data.d;
      liveState[m[1]].lastUpdate = Date.now();
    }
  }

  function installFetchHook() {
    const origFetch = window.fetch;
    window.fetch = async function(input, init) {
      const url = input && input.url ? input.url : String(input);
      const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      try {
        const headers = normalizeHeaders((init && init.headers) || (input && input.headers));
        captureAuth(url, headers);
        if (String(url).includes('tradovateapi.com')) {
          maybeCaptureOrderTemplate(url, method, parseBody(init && init.body));
        }
      } catch {}
      const resp = await origFetch.apply(this, arguments);
      if (String(url).includes('tradovateapi.com') && resp.ok) {
        try {
          const clone = resp.clone();
          const ct = clone.headers.get('content-type') || '';
          if (ct.includes('json')) {
            clone.text().then(text => {
              try { updateCache(url, method, JSON.parse(text)); } catch {}
            }).catch(() => {});
          }
        } catch {}
      }
      return resp;
    };
  }

  function authStatus() {
    if (!auth.jwt) return { loggedIn: false };
    let expired = false;
    try {
      const payload = JSON.parse(atob(auth.jwt.split('.')[1]));
      expired = payload.exp ? Math.floor(Date.now() / 1000) >= payload.exp : false;
    } catch {}
    return {
      loggedIn: !expired,
      expired,
      isDemo: auth.isDemo,
      capturedAt: auth.capturedAt,
      baseUrl: auth.baseUrl
    };
  }

  async function ensureAccounts() {
    if (accounts && accounts.length) return accounts;
    const a = authStatus();
    if (!a.loggedIn) throw new Error('Tradovate login not detected in TradingView');
    const res = await fetch(auth.baseUrl + '/accounts?locale=en&requestId=' + COPY_TAG + '_accounts_' + Date.now(), {
      headers: { Authorization: 'Bearer ' + auth.jwt, Accept: 'application/json' }
    });
    const json = await res.json();
    accounts = json.d || json;
    return accounts;
  }

  async function accountId() {
    const list = await ensureAccounts();
    const first = Array.isArray(list) ? list[0] : null;
    if (!first || !first.id) throw new Error('No Tradovate account found');
    return String(first.id);
  }

  async function refreshAccount(accId) {
    const headers = { Authorization: 'Bearer ' + auth.jwt, Accept: 'application/json' };
    const base = auth.baseUrl + '/accounts/' + accId;
    await Promise.allSettled([
      fetch(base + '/orders?locale=en&requestId=' + COPY_TAG + '_refresh_o_' + Date.now(), { headers }),
      fetch(base + '/positions?locale=en&requestId=' + COPY_TAG + '_refresh_p_' + Date.now(), { headers }),
      fetch(base + '/state?locale=en&requestId=' + COPY_TAG + '_refresh_s_' + Date.now(), { headers })
    ]);
  }

  function bracketKeys(body) {
    const keys = Object.keys(body || {});
    return {
      entry: keys.filter(k => /^(price|limitPrice|limit_price)$/i.test(k) || (/price/i.test(k) && !/stop|loss|profit|take|tp|sl/i.test(k))),
      stop: keys.filter(k => /stop|loss|sl/i.test(k)),
      profit: keys.filter(k => /profit|take|tp|target/i.test(k))
    };
  }

  function sameInstrument(value, symbol) {
    if (!value || !symbol) return false;
    return String(value).toUpperCase() === String(symbol).toUpperCase();
  }

  function orderInstrument(order) {
    return order && (order.instrument || order.symbol || order.contract);
  }

  function positionInstrument(position) {
    return position && (position.instrument || position.symbol || position.contract);
  }

  function positionQty(position) {
    if (!position) return 0;
    const raw = Number(position.qty ?? position.netPos ?? 0);
    if (!raw) return 0;
    const side = String(position.side || '').toLowerCase();
    if (side === 'sell' || side === 'short') return -Math.abs(raw);
    if (side === 'buy' || side === 'long') return Math.abs(raw);
    return raw;
  }

  function directionForQty(qty) {
    if (qty > 0) return 'long';
    if (qty < 0) return 'short';
    return '';
  }

  function workingOrdersForSymbol(state, symbol) {
    const orders = Array.isArray(state.orders) ? state.orders : [];
    return orders.filter(o => {
      const status = String(o.status || o.ordStatus || '').toLowerCase();
      if (status && status !== 'working' && status !== 'pending' && status !== 'pendingnew') return false;
      return sameInstrument(orderInstrument(o), symbol);
    });
  }

  function orderText(order) {
    return Object.entries(order || {})
      .map(([k, v]) => `${k}:${v}`)
      .join(' ')
      .toLowerCase();
  }

  function isStopOrder(order) {
    return /stop|stoploss|loss|sl/.test(orderText(order));
  }

  function isProfitOrder(order) {
    return /profit|target|takeprofit|take profit|tp/.test(orderText(order));
  }

  function protectionSummary(state, symbol) {
    const working = workingOrdersForSymbol(state, symbol);
    const stopOrders = working.filter(isStopOrder);
    const profitOrders = working.filter(isProfitOrder);
    return {
      ok: stopOrders.length > 0,
      hasStop: stopOrders.length > 0,
      hasProfit: profitOrders.length > 0,
      workingOrders: working.length,
      stopOrders: stopOrders.length,
      profitOrders: profitOrders.length
    };
  }

  function positionForSymbol(state, symbol) {
    const positions = Array.isArray(state.positions) ? state.positions : [];
    return positions.find(p => sameInstrument(positionInstrument(p), symbol) && positionQty(p) !== 0) || null;
  }

  function firstUnprotectedPosition(state) {
    const positions = Array.isArray(state.positions) ? state.positions : [];
    for (const position of positions) {
      const symbol = positionInstrument(position);
      const qty = positionQty(position);
      if (!symbol || !qty) continue;
      const protection = protectionSummary(state, symbol);
      if (!protection.hasStop) {
        return {
          symbol,
          qty,
          direction: directionForQty(qty),
          protection,
          position
        };
      }
    }
    return null;
  }

  async function cancelWorkingOrders(accId, state, symbol) {
    const headers = { Authorization: 'Bearer ' + auth.jwt, Accept: 'application/json' };
    const results = [];
    for (const o of workingOrdersForSymbol(state, symbol)) {
      const id = o.id || o.orderId;
      if (!id) continue;
      const r = await fetch(auth.baseUrl + '/accounts/' + accId + '/orders/' + id + '?locale=en&requestId=' + COPY_TAG + '_replace_cancel_' + Date.now(), {
        method: 'DELETE',
        headers
      });
      results.push({ id, ok: r.ok });
    }
    return results;
  }

  function buildOrderBody(signal) {
    const base = orderTemplate && orderTemplate.body ? { ...orderTemplate.body } : {};
    const keys = bracketKeys(base);
    if (orderTemplate && (!keys.stop.length || !keys.profit.length)) {
      throw new Error('Captured template does not contain bracket stop/profit fields');
    }
    if (!orderTemplate) {
      throw new Error('No bracket template. In demo, manually place one bracket order from TradingView first so MSS can learn the request shape.');
    }

    const side = signal.direction === 'long' ? 'buy' : 'sell';
    base.instrument = signal.symbol;
    base.symbol = signal.symbol;
    base.contract = signal.symbol;
    base.qty = String(signal.qty);
    base.quantity = String(signal.qty);
    base.side = side;
    base.action = side;
    base.type = 'limit';
    base.orderType = 'limit';
    base.durationType ||= 'Day';

    const entryKeys = keys.entry.length ? keys.entry : ['price'];
    entryKeys.forEach(k => { base[k] = String(signal.entry); });
    keys.stop.forEach(k => { base[k] = String(signal.sl); });
    keys.profit.forEach(k => { base[k] = String(signal.tp); });
    return base;
  }

  async function placeSignal(task) {
    const a = authStatus();
    if (!a.loggedIn) throw new Error('Tradovate login not detected or expired');
    const accId = await accountId();
    const signal = task.payload;
    const key = waveKey(signal);
    if (waveLedger[key] && waveLedger[key].status === 'consumed') {
      return {
        ok: true,
        skipped: true,
        reason: 'wave already consumed',
        waveId: key,
        consumedAt: waveLedger[key].consumedAt
      };
    }
    await refreshAccount(accId);
    const state = liveState[accId] || {};
    const currentPosition = positionForSymbol(state, signal.symbol);
    if (currentPosition) {
      const currentDirection = directionForQty(positionQty(currentPosition));
      if (currentDirection && currentDirection !== signal.direction) {
        return {
          ok: true,
          skipped: true,
          reason: 'opposite signal ignored while holding existing position',
          accountId: accId,
          currentDirection,
          signalDirection: signal.direction
        };
      }
    } else {
      await cancelWorkingOrders(accId, state, signal.symbol);
      await refreshAccount(accId);
    }
    const bodyObj = buildOrderBody(signal);
    const reqId = COPY_TAG + '_entry_' + Date.now();
    const res = await fetch(auth.baseUrl + '/accounts/' + accId + '/orders?locale=en&requestId=' + reqId, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + auth.jwt,
        Accept: 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: encodeBody(bodyObj)
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || json.s === 'error') {
      throw new Error(json.errmsg || json.errorText || json.failureText || 'order rejected');
    }
    const workingWaveId = markWaveWorking(signal, { orderResponse: json, signalType: signal.type });
    await refreshAccount(accId);
    const refreshedState = liveState[accId] || {};
    const positionAfterOrder = positionForSymbol(refreshedState, signal.symbol);
    if (positionAfterOrder) markWaveConsumed(signal, { orderResponse: json, signalType: signal.type });
    const protection = protectionSummary(refreshedState, signal.symbol);
    const shouldCheckProtection = !signal.safety || signal.safety.bracketProtectionCheck !== false;
    if (shouldCheckProtection && positionAfterOrder && !protection.hasStop) {
      return {
        ok: false,
        error: 'bracket protection check failed: position exists but no stop order detected',
        accountId: accId,
        waveId: workingWaveId,
        protection,
        position: positionAfterOrder,
        response: json,
        bodyKeys: Object.keys(bodyObj),
        templateCapturedAt: orderTemplate.capturedAt
      };
    }
    return { ok: true, accountId: accId, waveId: workingWaveId, response: json, protection, bodyKeys: Object.keys(bodyObj), templateCapturedAt: orderTemplate.capturedAt };
  }

  async function flattenTask() {
    const a = authStatus();
    if (!a.loggedIn) throw new Error('Tradovate login not detected or expired');
    const accId = await accountId();
    await refreshAccount(accId);
    const state = liveState[accId] || {};
    const orders = Array.isArray(state.orders) ? state.orders : [];
    const positions = Array.isArray(state.positions) ? state.positions : [];
    const headers = { Authorization: 'Bearer ' + auth.jwt, Accept: 'application/json' };
    const results = [];
    for (const o of orders) {
      const status = String(o.status || o.ordStatus || '').toLowerCase();
      if (status && status !== 'working') continue;
      const id = o.id || o.orderId;
      if (!id) continue;
      const r = await fetch(auth.baseUrl + '/accounts/' + accId + '/orders/' + id + '?locale=en&requestId=' + COPY_TAG + '_cancel_' + Date.now(), {
        method: 'DELETE',
        headers
      });
      results.push({ type: 'cancel', id, ok: r.ok });
    }
    for (const p of positions) {
      const qty = Number(p.qty || p.netPos || 0);
      const id = p.id || p.positionId;
      if (!id || !qty) continue;
      const r = await fetch(auth.baseUrl + '/accounts/' + accId + '/positions/' + id + '?locale=en&requestId=' + COPY_TAG + '_flat_' + Date.now(), {
        method: 'DELETE',
        headers
      });
      results.push({ type: 'flatten', id, ok: r.ok });
    }
    await refreshAccount(accId);
    return { ok: true, accountId: accId, results };
  }

  async function historyProbeTask(task) {
    const a = authStatus();
    if (!a.loggedIn) throw new Error('Tradovate login not detected or expired');
    const symbol = (task.payload && task.payload.symbol) || 'MGC1!';
    const bars = Number((task.payload && task.payload.bars) || 500);
    const headers = {
      Authorization: 'Bearer ' + auth.jwt,
      Accept: 'application/json',
      'Content-Type': 'application/json'
    };
    const body = {
      symbol,
      chartDescription: {
        underlyingType: 'MinuteBar',
        elementSize: 5,
        elementSizeUnit: 'UnderlyingUnits'
      },
      timeRange: {
        asMuchAsElements: bars
      }
    };
    const endpoints = [
      auth.baseUrl + '/md/getChart?locale=en&requestId=' + COPY_TAG + '_hist_' + Date.now(),
      auth.baseUrl.replace('trader.', 'md.').replace('demo.', 'md-demo.') + '/v1/md/getChart?locale=en&requestId=' + COPY_TAG + '_hist_' + Date.now(),
      auth.baseUrl.replace('/v1', '') + '/v1/md/getChart?locale=en&requestId=' + COPY_TAG + '_hist_' + Date.now()
    ];
    const attempts = [];
    for (const url of Array.from(new Set(endpoints))) {
      try {
        const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
        const text = await res.text();
        let json = null;
        try { json = JSON.parse(text); } catch {}
        const rows = json && json.d && Array.isArray(json.d.charts) ? json.d.charts.length
          : json && Array.isArray(json.d) ? json.d.length
            : json && Array.isArray(json.bars) ? json.bars.length
              : 0;
        attempts.push({
          url: url.replace(/[?].*$/, ''),
          status: res.status,
          ok: res.ok,
          rows,
          keys: json && typeof json === 'object' ? Object.keys(json).slice(0, 12) : [],
          preview: text.slice(0, 500)
        });
        if (res.ok && rows > 0) {
          return {
            ok: true,
            symbol,
            barsRequested: bars,
            endpoint: url.replace(/[?].*$/, ''),
            rows,
            responseKeys: Object.keys(json || {}),
            preview: text.slice(0, 1000)
          };
        }
      } catch (err) {
        attempts.push({ url: url.replace(/[?].*$/, ''), ok: false, error: err.message || String(err) });
      }
    }
    return { ok: false, error: 'no Tradovate history endpoint returned bars', symbol, barsRequested: bars, baseUrl: auth.baseUrl, attempts };
  }

  window.addEventListener('message', async function(event) {
    const data = event.data || {};
    if (data.source !== 'mss-relay-client') return;
    const requestId = data.payload && data.payload.requestId;
    function reply(payload) {
      window.postMessage({ source: 'mss-tradovate-bridge', requestId, payload }, '*');
    }
    try {
      if (data.action === 'status') {
        let unprotectedPosition = null;
        try {
          const accId = await accountId();
          await refreshAccount(accId);
          const state = liveState[accId] || {};
          unprotectedPosition = firstUnprotectedPosition(state);
          if (unprotectedPosition) unprotectedPosition.accountId = accId;
        } catch {}
        reply({ ok: true, auth: authStatus(), accounts, templateReady: !!orderTemplate, templateCapturedAt: orderTemplate && orderTemplate.capturedAt, consumedWaves: Object.keys(waveLedger).length, unprotectedPosition });
      } else if (data.action === 'executeSignal') {
        reply(await placeSignal(data.payload.task));
      } else if (data.action === 'flatten') {
        reply(await flattenTask());
      } else if (data.action === 'historyProbe') {
        reply(await historyProbeTask(data.payload.task));
      }
    } catch (err) {
      reply({ ok: false, error: err.message || String(err) });
    }
  });

  installFetchHook();
  log('loaded. Manually place one demo bracket order if templateReady=false.');
})();
