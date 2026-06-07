import { addEvent, saveState } from './store.js';
import { beijingParts, isBlockedTradingWindow, signalAgeSeconds } from './time.js';

function roundPrice(n) {
  return Math.round(Number(n) * 10) / 10;
}

function normalizeDirection(value) {
  if (value === 'bullish' || value === 'buy' || value === 'long') return 'long';
  if (value === 'bearish' || value === 'sell' || value === 'short') return 'short';
  return '';
}

function signalId(signal) {
  return String(signal.id || `${signal.strategy || 'mss'}:${signal.direction}:${signal.time}:${signal.entry}:${signal.sl}:${signal.tp}`);
}

function newTask(kind, payload) {
  return {
    id: `${kind}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    kind,
    payload,
    status: 'pending',
    createdAt: new Date().toISOString(),
    dispatchedAt: null,
    completedAt: null,
    attempts: 0,
    lastError: ''
  };
}

function sameWave(a, b) {
  if (!a || !b) return false;
  return String(a.waveId || '') === String(b.waveId || '');
}

export class RelayEngine {
  constructor({ config, state }) {
    this.config = config;
    this.state = state;
    this.flattenedForDate = '';
    this.state.tasks ||= [];
    this.state.extension ||= { lastSeenAt: null, auth: null, account: null, message: '' };
  }

  status() {
    return {
      config: {
        server: this.config.server,
        strategy: this.config.strategy
      },
      state: this.state,
      time: {
        beijing: beijingParts(),
        blocked: isBlockedTradingWindow(this.config)
      }
    };
  }

  validateSignal(signal) {
    if (signal.secret !== this.config.server.webhookSecret) {
      const preview = signal.secret == null ? '<missing>' : String(signal.secret).slice(0, 40);
      throw new Error(`bad webhook secret: received "${preview}"`);
    }
    const direction = normalizeDirection(signal.direction || signal.side);
    if (!direction) throw new Error('bad direction');
    for (const key of ['entry', 'sl', 'tp', 'waveStart', 'waveEnd']) {
      if (!Number.isFinite(Number(signal[key]))) throw new Error(`missing numeric ${key}`);
    }
    return {
      ...signal,
      id: signalId(signal),
      direction,
      symbol: this.config.strategy.contract,
      qty: Number(this.config.strategy.qty),
      waveId: signal.waveId || `${direction}:${signal.waveStartBar ?? signal.waveStart}`,
      waveStartBar: signal.waveStartBar,
      entry: roundPrice(signal.entry),
      sl: roundPrice(signal.sl),
      tp: roundPrice(signal.tp),
      waveStart: roundPrice(signal.waveStart),
      waveEnd: roundPrice(signal.waveEnd),
      type: signal.type || 'structure',
      safety: {
        bracketProtectionCheck: this.config.strategy.bracketProtectionCheck !== false
      }
    };
  }

  riskBlocked() {
    const s = this.config.strategy;
    if (!s.enabled) return 'auto trading is OFF';
    if (this.state.risk.pausedReason) return this.state.risk.pausedReason;
    if (isBlockedTradingWindow(this.config)) return 'blocked Beijing time window';
    if (Number(this.state.risk.dailyPnl) <= -Math.abs(Number(s.dailyLossLimit))) return 'daily loss limit hit';
    if (Number(this.state.risk.dailyPnl) >= Math.abs(Number(s.dailyProfitLimit))) return 'daily profit target hit';
    if (Number(this.state.risk.consecutiveLosses) >= Number(s.maxConsecutiveLosses)) return 'consecutive loss limit hit';
    return '';
  }

  resetDailyIfNeeded() {
    const now = beijingParts();
    if (this.state.risk.beijingDate === now.date) return;
    if (now.hour < Number(this.config.strategy.resetHourBeijing)) return;
    this.state.risk = {
      beijingDate: now.date,
      baselineNetLiq: null,
      dailyPnl: 0,
      consecutiveLosses: 0,
      pausedReason: ''
    };
    addEvent(this.state, { level: 'info', message: `Beijing daily reset ${now.date}` });
  }

  ingestSignal(rawSignal) {
    this.resetDailyIfNeeded();
    const signal = this.validateSignal(rawSignal);
    this.state.lastSignal = signal;

    if (this.state.seenSignals[signal.id]) {
      addEvent(this.state, { level: 'warn', message: 'duplicate signal skipped', signal });
      return { ok: false, skipped: true, reason: 'duplicate signal' };
    }
    this.state.seenSignals[signal.id] = Date.now();

    const age = signalAgeSeconds(signal);
    if (age > Number(this.config.strategy.maxSignalAgeSeconds)) {
      addEvent(this.state, { level: 'warn', message: `stale signal skipped: ${age}s`, signal });
      saveState(this.state);
      return { ok: false, skipped: true, reason: `stale signal ${age}s` };
    }

    const blocked = this.riskBlocked();
    if (blocked) {
      addEvent(this.state, { level: 'warn', message: `signal blocked: ${blocked}`, signal });
      saveState(this.state);
      return { ok: false, skipped: true, reason: blocked };
    }

    if (signal.type === 'wave_update') {
      this.state.tasks = this.state.tasks.filter(task => {
        if (task.kind !== 'signal') return true;
        if (!sameWave(task.payload, signal)) return true;
        return task.status !== 'pending';
      });
    }

    const task = newTask('signal', signal);
    this.state.tasks.unshift(task);
    this.state.tasks = this.state.tasks.slice(0, 200);
    addEvent(this.state, { level: 'info', message: 'signal queued for extension', signal, taskId: task.id });
    saveState(this.state);
    return { ok: true, queued: true, task };
  }

  nextTask(clientId) {
    this.resetDailyIfNeeded();
    const now = Date.now();
    const task = [...this.state.tasks].reverse().find(t => {
      if (t.status === 'pending') return true;
      if (t.status === 'dispatched' && t.dispatchedAt && now - Date.parse(t.dispatchedAt) > 30_000) return true;
      return false;
    });
    if (!task) {
      saveState(this.state);
      return { ok: true, task: null };
    }
    task.status = 'dispatched';
    task.dispatchedAt = new Date().toISOString();
    task.attempts += 1;
    task.clientId = clientId || 'unknown';
    saveState(this.state);
    return { ok: true, task };
  }

  reportTask(report) {
    this.state.extension.lastSeenAt = new Date().toISOString();
    const task = this.state.tasks.find(t => t.id === report.taskId);
    if (task) {
      task.status = report.ok ? 'completed' : 'error';
      task.completedAt = new Date().toISOString();
      task.lastError = report.ok ? '' : (report.error || report.message || 'unknown error');
      task.result = report.result || null;
    }
    if (typeof report.dailyPnl === 'number') this.state.risk.dailyPnl = report.dailyPnl;
    if (typeof report.consecutiveLosses === 'number') this.state.risk.consecutiveLosses = report.consecutiveLosses;
    addEvent(this.state, {
      level: report.ok ? 'info' : 'error',
      message: report.message || (report.ok ? 'extension task completed' : 'extension task failed'),
      report
    });
    saveState(this.state);
    return { ok: true };
  }

  reportStatus(status) {
    const unprotected = status.unprotectedPosition || null;
    this.state.extension = {
      ...this.state.extension,
      ...status,
      lastSeenAt: new Date().toISOString()
    };
    if (unprotected && this.config.strategy.unprotectedPositionCheck !== false) {
      const key = `${unprotected.accountId || 'account'}:${unprotected.symbol || this.config.strategy.contract}:${unprotected.qty || ''}:${unprotected.direction || ''}`;
      if (this.state.lastUnprotectedPositionKey !== key) {
        this.state.lastUnprotectedPositionKey = key;
        addEvent(this.state, {
          level: 'error',
          message: `UNPROTECTED POSITION: ${unprotected.symbol || this.config.strategy.contract} ${unprotected.direction || ''} qty ${unprotected.qty || ''} has no detected stop order`,
          unprotected
        });
        if (this.config.strategy.flattenUnprotectedPosition === true) {
          const task = newTask('flatten', { reason: 'unprotected position detected', contract: unprotected.symbol || this.config.strategy.contract });
          this.state.tasks.unshift(task);
          addEvent(this.state, { level: 'warn', message: 'flatten queued for unprotected position', taskId: task.id, unprotected });
        }
      }
    } else {
      this.state.lastUnprotectedPositionKey = '';
    }
    saveState(this.state);
    return { ok: true };
  }

  queueFlatten() {
    const task = newTask('flatten', { reason: 'manual flatten', contract: this.config.strategy.contract });
    this.state.tasks.unshift(task);
    addEvent(this.state, { level: 'warn', message: 'flatten queued for extension', taskId: task.id });
    saveState(this.state);
    return { ok: true, task };
  }

  queueHistoryProbe(params = {}) {
    const task = newTask('historyProbe', {
      symbol: params.symbol || this.config.strategy.contract,
      bars: Number(params.bars || 500),
      reason: 'manual Tradovate history probe'
    });
    this.state.tasks.unshift(task);
    addEvent(this.state, { level: 'info', message: 'history probe queued for extension', taskId: task.id, payload: task.payload });
    saveState(this.state);
    return { ok: true, task };
  }

  scheduledTasks() {
    this.resetDailyIfNeeded();
    const now = beijingParts();
    if (now.hour === Number(this.config.strategy.blockedStartHourBeijing) && this.flattenedForDate !== now.date) {
      this.flattenedForDate = now.date;
      const task = newTask('flatten', { reason: 'scheduled Beijing 04:00 flatten', contract: this.config.strategy.contract });
      this.state.tasks.unshift(task);
      addEvent(this.state, { level: 'warn', message: 'scheduled Beijing 04:00 flatten queued', taskId: task.id });
      saveState(this.state);
    }
  }
}
