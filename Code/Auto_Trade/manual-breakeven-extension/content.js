(function() {
  'use strict';

  if (window.__manualBreakevenContentLoaded) return;
  window.__manualBreakevenContentLoaded = true;

  const SOURCE_CONTENT = 'manual-be-content';
  const SOURCE_PAGE = 'manual-be-page';
  let busy = false;

  function injectBridge() {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('page-bridge.js');
    script.onload = () => script.remove();
    (document.documentElement || document.head).appendChild(script);
  }

  function askPage(action, payload = {}, timeoutMs = 15000) {
    return new Promise((resolve) => {
      const requestId = Date.now() + '-' + Math.random().toString(16).slice(2);
      const timer = setTimeout(() => {
        window.removeEventListener('message', onMessage);
        resolve({ ok: false, error: 'page bridge timeout' });
      }, timeoutMs);

      function onMessage(event) {
        const data = event.data || {};
        if (data.source !== SOURCE_PAGE || data.requestId !== requestId) return;
        clearTimeout(timer);
        window.removeEventListener('message', onMessage);
        resolve(data.payload || { ok: false, error: 'empty page bridge response' });
      }

      window.addEventListener('message', onMessage);
      window.postMessage({ source: SOURCE_CONTENT, action, requestId, payload }, '*');
    });
  }

  async function saveStatus(status) {
    await chrome.storage.local.set({ lastStatus: { ...status, updatedAt: Date.now() } });
  }

  async function getStatus() {
    const status = await askPage('status', {}, 8000);
    await saveStatus(status);
    return status;
  }

  async function updateTask(id, patch) {
    const data = await chrome.storage.local.get({ breakevenTasks: [] });
    const tasks = (data.breakevenTasks || []).map(task => task.id === id ? { ...task, ...patch, updatedAt: Date.now() } : task);
    await chrome.storage.local.set({ breakevenTasks: tasks });
  }

  async function monitorTasks() {
    if (busy) return;
    busy = true;
    try {
      await getStatus();
      const data = await chrome.storage.local.get({ breakevenTasks: [] });
      const tasks = (data.breakevenTasks || []).filter(t => t.status === 'pending');
      for (const task of tasks) {
        const result = await askPage('manualBreakeven', { task }, 20000);
        if (result.pending) {
          await updateTask(task.id, {
            lastMessage: result.reason || '等待触发价',
            breakevenPrice: result.breakevenPrice || task.breakevenPrice || task.entryPrice,
            position: result.position || task.position
          });
        } else if (result.ok) {
          await updateTask(task.id, {
            status: 'done',
            lastMessage: result.reason || '已推保',
            breakevenPrice: result.breakevenPrice,
            result
          });
        } else {
          await updateTask(task.id, {
            status: 'error',
            lastMessage: result.error || '推保失败',
            result
          });
        }
      }
    } finally {
      busy = false;
    }
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !String(message.type || '').startsWith('manual-be:')) return false;
    (async () => {
      if (message.type === 'manual-be:getStatus') {
        sendResponse(await getStatus());
      } else if (message.type === 'manual-be:wake') {
        monitorTasks();
        sendResponse({ ok: true });
      } else {
        sendResponse({ ok: false, error: 'unknown message type' });
      }
    })().catch(err => sendResponse({ ok: false, error: err.message || String(err) }));
    return true;
  });

  injectBridge();
  setInterval(monitorTasks, 1500);
  setTimeout(monitorTasks, 800);
})();
