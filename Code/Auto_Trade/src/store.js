import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const STORE_PATH = path.join(ROOT, 'data', 'state.json');

const DEFAULT_STATE = {
  seenSignals: {},
  tasks: [],
  events: [],
  activeOrders: [],
  extension: {
    lastSeenAt: null,
    auth: null,
    account: null,
    message: ''
  },
  risk: {
    beijingDate: '',
    baselineNetLiq: null,
    dailyPnl: 0,
    consecutiveLosses: 0,
    pausedReason: ''
  },
  lastSignal: null,
  lastAuth: null
};

export function loadState() {
  if (!fs.existsSync(STORE_PATH)) return structuredClone(DEFAULT_STATE);
  try {
    return { ...structuredClone(DEFAULT_STATE), ...JSON.parse(fs.readFileSync(STORE_PATH, 'utf8')) };
  } catch {
    return structuredClone(DEFAULT_STATE);
  }
}

export function saveState(state) {
  fs.mkdirSync(path.dirname(STORE_PATH), { recursive: true });
  fs.writeFileSync(STORE_PATH, JSON.stringify(state, null, 2) + '\n');
}

export function addEvent(state, event) {
  state.events.unshift({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    at: new Date().toISOString(),
    ...event
  });
  state.events = state.events.slice(0, 200);
  saveState(state);
}
