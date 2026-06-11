(function() {
  'use strict';

  if (window.__manualBreakevenPageBridgeLoaded) return;
  window.__manualBreakevenPageBridgeLoaded = true;

  const SOURCE_CONTENT = 'manual-be-content';
  const SOURCE_PAGE = 'manual-be-page';
  const COPY_TAG = 'manualbe';

  let auth = { jwt: null, baseUrl: null, isDemo: null, capturedAt: null };
  let accounts = null;
  const liveState = {};

  function normalizeHeaders(headers) {
    const out = {};
    try {
      if (headers instanceof Headers) {
        for (const [k, v] of headers.entries()) out[k.toLowerCase()] = v;
        return out;
      }
    } catch {}
    if (headers && typeof headers === 'object') {
      Object.keys(headers).forEach(k => { out[k.toLowerCase()] = String(headers[k]); });
    }
    return out;
  }

  function captureAuth(url, headers) {
    if (!String(url).includes('tradovateapi.com')) return;
    const raw = headers.authorization;
    if (!raw) return;
    const match = raw.match(/^Bearer\s+(.+)$/i);
    if (!match) return;
    const base = String(url).match(/^(https?:\/\/[^/]+)/)?.[1];
    auth = {
      jwt: match[1],
      baseUrl: base,
      isDemo: !!base && base.includes('demo'),
      capturedAt: Date.now()
    };
  }

  function updateCache(url, method, data) {
    if (!data || !data.d) return;
    if (/\/accounts(\?|$)/.test(url) && method === 'GET') {
      accounts = data.d;
      return;
    }
    const match = String(url).match(/\/accounts\/([^/?]+)\/(state|positions|orders|executions)/);
    if (match && method === 'GET') {
      liveState[match[1]] ||= {};
      liveState[match[1]][match[2]] = data.d;
      liveState[match[1]].lastUpdate = Date.now();
    }
  }

  function installFetchHook() {
    const originalFetch = window.fetch;
    window.fetch = async function(input, init) {
      const url = input && input.url ? input.url : String(input);
      const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      try {
        captureAuth(url, normalizeHeaders((init && init.headers) || (input && input.headers)));
      } catch {}
      const response = await originalFetch.apply(this, arguments);
      if (String(url).includes('tradovateapi.com') && response.ok) {
        try {
          const clone = response.clone();
          const contentType = clone.headers.get('content-type') || '';
          if (contentType.includes('json')) {
            clone.text().then(text => {
              try { updateCache(url, method, JSON.parse(text)); } catch {}
            }).catch(() => {});
          }
        } catch {}
      }
      return response;
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
    const status = authStatus();
    if (!status.loggedIn) throw new Error('Tradovate login not detected in TradingView');
    const response = await fetch(auth.baseUrl + '/accounts?locale=en&requestId=' + COPY_TAG + '_accounts_' + Date.now(), {
      headers: { Authorization: 'Bearer ' + auth.jwt, Accept: 'application/json' }
    });
    const json = await response.json();
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
      fetch(base + '/orders?locale=en&requestId=' + COPY_TAG + '_orders_' + Date.now(), { headers }),
      fetch(base + '/positions?locale=en&requestId=' + COPY_TAG + '_positions_' + Date.now(), { headers }),
      fetch(base + '/state?locale=en&requestId=' + COPY_TAG + '_state_' + Date.now(), { headers })
    ]);
  }

  function sameInstrument(a, b) {
    if (!a || !b) return false;
    return String(a).toUpperCase() === String(b).toUpperCase();
  }

  function orderInstrument(order) {
    return order && (order.instrument || order.symbol || order.contract);
  }

  function positionInstrument(position) {
    return position && (position.instrument || position.symbol || position.contract);
  }

  function positionQty(position) {
    if (!position) return 0;
    const raw = Number(position.qty ?? position.netPos ?? position.position ?? 0);
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

  function orderText(order) {
    return Object.entries(order || {}).map(([k, v]) => `${k}:${v}`).join(' ').toLowerCase();
  }

  function isWorkingOrder(order) {
    const status = String(order.status || order.ordStatus || '').toLowerCase();
    return !status || status === 'working' || status === 'pending' || status === 'pendingnew' || status === 'accepted';
  }

  function workingOrdersForSymbol(state, symbol) {
    const orders = Array.isArray(state.orders) ? state.orders : [];
    return orders.filter(order => isWorkingOrder(order) && sameInstrument(orderInstrument(order), symbol));
  }

  function isStopOrder(order) {
    return /stop|stoploss|loss|sl/.test(orderText(order));
  }

  function isProfitOrder(order) {
    return /profit|target|takeprofit|take profit|tp/.test(orderText(order));
  }

  function numberOrNull(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function firstNumber(obj, keys) {
    if (!obj) return null;
    for (const key of keys) {
      if (Object.prototype.hasOwnProperty.call(obj, key)) {
        const n = numberOrNull(obj[key]);
        if (n !== null) return n;
      }
    }
    return null;
  }

  function positionEntryPrice(position) {
    return firstNumber(position, ['avgPrice', 'averagePrice', 'avgPx', 'netPrice', 'entryPrice', 'openPrice', 'price']);
  }

  function unrealizedPnl(position) {
    return firstNumber(position, ['unrealizedPnl', 'unrealizedPnL', 'openPnl', 'openPnL', 'pnl', 'profitAndLoss']);
  }

  function positionCurrentPrice(position, pointValue) {
    const direct = firstNumber(position, ['lastPrice', 'markPrice', 'marketPrice', 'currentPrice', 'close', 'last']);
    if (direct !== null) return direct;
    const entry = positionEntryPrice(position);
    const pnl = unrealizedPnl(position);
    const qty = positionQty(position);
    const dollarsPerPoint = Number(pointValue || 10);
    if (entry === null || pnl === null || !qty || !dollarsPerPoint) return null;
    const points = pnl / (Math.abs(qty) * dollarsPerPoint);
    return qty > 0 ? entry + points : entry - points;
  }

  function stopPrice(order) {
    return firstNumber(order, ['stopPrice', 'stopLoss', 'stop_loss', 'triggerPrice', 'activationPrice', 'price']);
  }

  function targetPrice(order) {
    return firstNumber(order, ['takeProfit', 'takeProfitPrice', 'profitPrice', 'targetPrice', 'limitPrice', 'price']);
  }

  function positionForSymbol(state, symbol) {
    const positions = Array.isArray(state.positions) ? state.positions : [];
    return positions.find(position => sameInstrument(positionInstrument(position), symbol) && positionQty(position) !== 0) || null;
  }

  function roundTick(price) {
    return Math.round(Number(price) * 10) / 10;
  }

  function positionSummary(state, position, pointValue) {
    const symbol = positionInstrument(position);
    const working = workingOrdersForSymbol(state, symbol);
    const stopOrders = working.filter(isStopOrder);
    const profitOrders = working.filter(isProfitOrder);
    const qty = positionQty(position);
    return {
      symbol,
      qty,
      direction: directionForQty(qty),
      entryPrice: positionEntryPrice(position),
      currentPrice: positionCurrentPrice(position, pointValue),
      stopPrice: stopOrders.length ? stopPrice(stopOrders[0]) : null,
      targetPrice: profitOrders.length ? targetPrice(profitOrders[0]) : null,
      stopOrders: stopOrders.length,
      profitOrders: profitOrders.length,
      rawPosition: position
    };
  }

  function allPositionSummaries(state, pointValue) {
    const positions = Array.isArray(state.positions) ? state.positions : [];
    return positions
      .filter(position => positionInstrument(position) && positionQty(position) !== 0)
      .map(position => positionSummary(state, position, pointValue));
  }

  function encodeBody(obj) {
    const params = new URLSearchParams();
    Object.keys(obj || {}).forEach(key => {
      if (obj[key] !== undefined && obj[key] !== null && obj[key] !== '') params.append(key, String(obj[key]));
    });
    return params.toString();
  }

  function scalarOrderBody(order) {
    const omit = /^(id|orderId|status|ordStatus|filled|remaining|created|updated|timestamp|time|account|accountId|reject|error|message|children|legs)$/i;
    const out = {};
    for (const [key, value] of Object.entries(order || {})) {
      if (omit.test(key)) continue;
      if (value === null || value === undefined) continue;
      if (typeof value === 'object') continue;
      out[key] = String(value);
    }
    return out;
  }

  function setStopBodyPrice(body, price) {
    const keys = Object.keys(body);
    const priceKeys = keys.filter(key => /stop|trigger|activation|price/i.test(key) && !/profit|target|take/i.test(key));
    const targets = priceKeys.length ? priceKeys : ['stopPrice', 'price'];
    targets.forEach(key => { body[key] = String(price); });
    return body;
  }

  function buildReplacementStopBody(stopOrder, position, symbol, price) {
    const body = setStopBodyPrice(scalarOrderBody(stopOrder), price);
    body.instrument ||= symbol;
    body.symbol ||= symbol;
    body.contract ||= symbol;
    body.qty ||= String(Math.abs(positionQty(position)));
    body.quantity ||= String(Math.abs(positionQty(position)));
    body.side ||= positionQty(position) > 0 ? 'sell' : 'buy';
    body.action ||= body.side;
    body.type ||= 'stop';
    body.orderType ||= 'stop';
    body.durationType ||= 'Day';
    return body;
  }

  async function modifyStopOrder(accId, stopOrder, position, symbol, price) {
    const id = stopOrder.id || stopOrder.orderId;
    if (!id) throw new Error('stop order has no id');
    const headers = {
      Authorization: 'Bearer ' + auth.jwt,
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded'
    };
    const updateBody = setStopBodyPrice({}, price);
    const attempts = [];

    for (const method of ['PATCH', 'PUT']) {
      const response = await fetch(auth.baseUrl + '/accounts/' + accId + '/orders/' + id + '?locale=en&requestId=' + COPY_TAG + '_move_' + Date.now(), {
        method,
        headers,
        body: encodeBody(updateBody)
      });
      const text = await response.text();
      let json = null;
      try { json = JSON.parse(text); } catch {}
      attempts.push({ method, status: response.status, ok: response.ok, preview: text.slice(0, 250) });
      if (response.ok && (!json || json.s !== 'error')) return { method, id, response: json || text };
    }

    const replacementBody = buildReplacementStopBody(stopOrder, position, symbol, price);
    const place = await fetch(auth.baseUrl + '/accounts/' + accId + '/orders?locale=en&requestId=' + COPY_TAG + '_new_stop_' + Date.now(), {
      method: 'POST',
      headers,
      body: encodeBody(replacementBody)
    });
    const placeText = await place.text();
    let placeJson = null;
    try { placeJson = JSON.parse(placeText); } catch {}
    attempts.push({ method: 'POST replacement', status: place.status, ok: place.ok, preview: placeText.slice(0, 250) });
    if (!place.ok || (placeJson && placeJson.s === 'error')) {
      throw new Error('failed to move stop; attempts=' + JSON.stringify(attempts));
    }

    const cancel = await fetch(auth.baseUrl + '/accounts/' + accId + '/orders/' + id + '?locale=en&requestId=' + COPY_TAG + '_cancel_old_' + Date.now(), {
      method: 'DELETE',
      headers: { Authorization: 'Bearer ' + auth.jwt, Accept: 'application/json' }
    });
    return {
      method: 'POST replacement then DELETE old stop',
      oldStopId: id,
      replacement: placeJson || placeText,
      cancelOldOk: cancel.ok,
      attempts
    };
  }

  async function statusPayload() {
    const status = authStatus();
    if (!status.loggedIn) return { ok: true, auth: status, positions: [], updatedAt: Date.now() };
    const accId = await accountId();
    await refreshAccount(accId);
    const state = liveState[accId] || {};
    return {
      ok: true,
      auth: status,
      accountId: accId,
      positions: allPositionSummaries(state, 10),
      updatedAt: Date.now()
    };
  }

  async function manualBreakeven(task) {
    const status = authStatus();
    if (!status.loggedIn) throw new Error('Tradovate login not detected in TradingView');
    const symbol = task.symbol;
    const triggerPrice = Number(task.triggerPrice);
    if (!symbol) throw new Error('task symbol missing');
    if (!Number.isFinite(triggerPrice)) throw new Error('triggerPrice missing');

    const accId = await accountId();
    await refreshAccount(accId);
    const state = liveState[accId] || {};
    const position = positionForSymbol(state, symbol);
    if (!position) return { ok: false, error: 'no open position for ' + symbol };

    const summary = positionSummary(state, position, 10);
    if (!summary.direction) return { ok: false, error: 'could not detect position direction', position: summary };
    if (!Number.isFinite(summary.entryPrice)) return { ok: false, error: 'could not detect entry price', position: summary };
    if (!Number.isFinite(summary.currentPrice)) {
      return { ok: true, pending: true, reason: '等待当前价', position: summary };
    }

    const reached = summary.direction === 'long'
      ? summary.currentPrice >= triggerPrice
      : summary.currentPrice <= triggerPrice;
    const breakevenPrice = summary.direction === 'long'
      ? roundTick(summary.entryPrice)
      : roundTick(summary.entryPrice);

    if (!reached) {
      return {
        ok: true,
        pending: true,
        reason: `等待触发：当前 ${summary.currentPrice} / 触发 ${triggerPrice}`,
        position: summary,
        breakevenPrice
      };
    }

    const stopOrders = workingOrdersForSymbol(state, symbol).filter(isStopOrder);
    if (!stopOrders.length) return { ok: false, error: '触发价已到，但没有检测到工作中的止损单', position: summary };

    const currentStopPrice = stopPrice(stopOrders[0]);
    if (currentStopPrice !== null) {
      const alreadyProtected = summary.direction === 'long'
        ? currentStopPrice >= breakevenPrice
        : currentStopPrice <= breakevenPrice;
      if (alreadyProtected) {
        return {
          ok: true,
          reason: '止损已经在保本或更好位置',
          position: summary,
          currentStopPrice,
          breakevenPrice
        };
      }
    }

    const moved = await modifyStopOrder(accId, stopOrders[0], position, symbol, breakevenPrice);
    await refreshAccount(accId);
    return {
      ok: true,
      reason: '已推保',
      position: summary,
      previousStopPrice: currentStopPrice,
      breakevenPrice,
      moved
    };
  }

  window.addEventListener('message', async (event) => {
    const data = event.data || {};
    if (data.source !== SOURCE_CONTENT) return;
    const requestId = data.requestId;
    const reply = (payload) => window.postMessage({ source: SOURCE_PAGE, requestId, payload }, '*');

    try {
      if (data.action === 'status') {
        reply(await statusPayload());
      } else if (data.action === 'manualBreakeven') {
        reply(await manualBreakeven(data.payload.task));
      } else {
        reply({ ok: false, error: 'unknown action' });
      }
    } catch (err) {
      reply({ ok: false, error: err.message || String(err) });
    }
  });

  installFetchHook();
})();
