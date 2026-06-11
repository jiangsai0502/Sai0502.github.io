import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { loadConfig, saveMutableConfig } from './config.js';
import { loadState, addEvent, saveState } from './store.js';
import { RelayEngine } from './relay.js';

const config = loadConfig();
const state = loadState();
const engine = new RelayEngine({ config, state });

const PUBLIC_DIR = path.join(process.cwd(), 'public');

function sendJson(res, status, data) {
  const body = JSON.stringify(data, null, 2);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body)
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => {
      body += chunk;
      if (body.length > 1024 * 1024) reject(new Error('body too large'));
    });
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

async function route(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (req.method === 'GET' && url.pathname === '/') {
    const html = fs.readFileSync(path.join(PUBLIC_DIR, 'index.html'));
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
    return;
  }

  if (req.method === 'GET' && url.pathname === '/app.js') {
    const js = fs.readFileSync(path.join(PUBLIC_DIR, 'app.js'));
    res.writeHead(200, { 'Content-Type': 'text/javascript; charset=utf-8' });
    res.end(js);
    return;
  }

  if (req.method === 'GET' && url.pathname === '/api/status') {
    sendJson(res, 200, engine.status());
    return;
  }

  if (req.method === 'POST' && url.pathname === '/api/config') {
    const patch = JSON.parse(await readBody(req) || '{}');
    Object.assign(config.strategy, patch.strategy || {});
    saveMutableConfig(config);
    addEvent(state, { level: 'info', message: 'strategy config updated', patch });
    sendJson(res, 200, engine.status());
    return;
  }

  if (req.method === 'POST' && url.pathname === '/webhook/tradingview') {
    try {
      const raw = await readBody(req);
      const signal = JSON.parse(raw);
      const result = engine.ingestSignal(signal);
      sendJson(res, result.ok ? 200 : 202, result);
    } catch (err) {
      addEvent(state, { level: 'error', message: `webhook error: ${err.message}` });
      sendJson(res, 400, { ok: false, error: err.message });
    }
    return;
  }

  if (req.method === 'POST' && url.pathname === '/api/flatten') {
    try {
      const result = engine.queueFlatten();
      sendJson(res, 200, { ok: true, result });
    } catch (err) {
      addEvent(state, { level: 'error', message: `manual flatten error: ${err.message}` });
      sendJson(res, 500, { ok: false, error: err.message });
    }
    return;
  }

  if (req.method === 'POST' && url.pathname === '/api/history-probe') {
    try {
      const params = JSON.parse(await readBody(req) || '{}');
      const result = engine.queueHistoryProbe(params);
      sendJson(res, 200, { ok: true, result });
    } catch (err) {
      addEvent(state, { level: 'error', message: `history probe error: ${err.message}` });
      sendJson(res, 500, { ok: false, error: err.message });
    }
    return;
  }

  if (req.method === 'POST' && url.pathname === '/api/manual-breakeven') {
    try {
      const params = JSON.parse(await readBody(req) || '{}');
      const result = engine.queueManualBreakeven(params);
      sendJson(res, 200, { ok: true, result });
    } catch (err) {
      addEvent(state, { level: 'error', message: `manual breakeven error: ${err.message}` });
      sendJson(res, 500, { ok: false, error: err.message });
    }
    return;
  }

  if (req.method === 'GET' && url.pathname === '/api/extension/next-task') {
    const clientId = url.searchParams.get('clientId') || '';
    sendJson(res, 200, engine.nextTask(clientId));
    return;
  }

  if (req.method === 'POST' && url.pathname === '/api/extension/report') {
    const report = JSON.parse(await readBody(req) || '{}');
    sendJson(res, 200, engine.reportTask(report));
    return;
  }

  if (req.method === 'POST' && url.pathname === '/api/extension/status') {
    const status = JSON.parse(await readBody(req) || '{}');
    sendJson(res, 200, engine.reportStatus(status));
    return;
  }

  sendJson(res, 404, { ok: false, error: 'not found' });
}

const server = http.createServer((req, res) => {
  route(req, res).catch(err => {
    addEvent(state, { level: 'error', message: `server error: ${err.message}` });
    sendJson(res, 500, { ok: false, error: err.message });
  });
});

server.listen(config.server.port, config.server.host, () => {
  console.log(`MSS Local Bot running at http://${config.server.host}:${config.server.port}`);
});

setInterval(() => {
  try {
    engine.scheduledTasks();
  } catch (err) {
    addEvent(state, { level: 'error', message: `scheduled task error: ${err.message}` });
  }
}, 60_000);
