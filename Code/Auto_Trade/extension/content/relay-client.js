(function() {
  'use strict';

  if (window.__mssRelayClientLoaded) return;
  window.__mssRelayClientLoaded = true;

  const RELAY = 'http://127.0.0.1:8787';
  const CLIENT_ID = 'mss-extension-' + Math.random().toString(16).slice(2);
  let busy = false;
  let lastStatusAt = 0;
  let lastPageStatus = null;

  function postToPage(action, payload) {
    window.postMessage({ source: 'mss-relay-client', action, payload }, '*');
  }

  function askPage(action, payload, timeoutMs = 15000) {
    return new Promise((resolve) => {
      const requestId = Date.now() + '-' + Math.random().toString(16).slice(2);
      const timer = setTimeout(() => {
        window.removeEventListener('message', onMessage);
        resolve({ ok: false, error: 'page bridge timeout' });
      }, timeoutMs);
      function onMessage(event) {
        const data = event.data || {};
        if (data.source !== 'mss-tradovate-bridge' || data.requestId !== requestId) return;
        clearTimeout(timer);
        window.removeEventListener('message', onMessage);
        resolve(data.payload || { ok: false, error: 'empty bridge response' });
      }
      window.addEventListener('message', onMessage);
      postToPage(action, { requestId, ...payload });
    });
  }

  async function relayPost(path, body) {
    const res = await fetch(RELAY + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
    return res.json().catch(() => ({}));
  }

  async function reportStatus() {
    const status = await askPage('status', {}, 5000);
    lastPageStatus = status;
    await relayPost('/api/extension/status', {
      clientId: CLIENT_ID,
      url: location.href,
      ...status
    });
  }

  async function poll() {
    if (busy) return;
    busy = true;
    try {
      if (Date.now() - lastStatusAt > 5000) {
        lastStatusAt = Date.now();
        await reportStatus();
      }
      if (!lastPageStatus || !lastPageStatus.auth || !lastPageStatus.auth.loggedIn || !lastPageStatus.templateReady) {
        return;
      }
      const res = await fetch(RELAY + '/api/extension/next-task?clientId=' + encodeURIComponent(CLIENT_ID));
      const payload = await res.json();
      const task = payload && payload.task;
      if (!task) return;

      const result = task.kind === 'flatten'
        ? await askPage('flatten', { task }, 60000)
        : task.kind === 'historyProbe'
          ? await askPage('historyProbe', { task }, 90000)
          : task.kind === 'manualBreakeven'
            ? await askPage('manualBreakeven', { task }, 60000)
            : await askPage('executeSignal', { task }, 60000);

      await relayPost('/api/extension/report', {
        clientId: CLIENT_ID,
        taskId: task.id,
        ok: !!result.ok,
        pending: !!result.pending,
        message: result.ok ? 'extension executed task' : (result.error || 'extension task failed'),
        result
      });
    } catch (err) {
      try {
        await relayPost('/api/extension/status', {
          clientId: CLIENT_ID,
          message: err.message || String(err)
        });
      } catch {}
    } finally {
      busy = false;
    }
  }

  setInterval(poll, 1500);
  setTimeout(poll, 500);
})();
