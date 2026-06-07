import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const DEFAULT_CONFIG = {
  server: {
    host: '127.0.0.1',
    port: 8787,
    webhookSecret: 'change-this-secret'
  },
  strategy: {
    enabled: false,
    contract: 'MGCM6',
    qty: 1,
    maxSameDirectionTrades: 2,
    maxSignalAgeSeconds: 60,
    retryAttempts: 10,
    dailyLossLimit: 300,
    dailyProfitLimit: 600,
    maxConsecutiveLosses: 10,
    blockedStartHourBeijing: 4,
    blockedEndHourBeijing: 7,
    resetHourBeijing: 7,
    flattenScope: 'account',
    bracketProtectionCheck: true,
    unprotectedPositionCheck: true,
    flattenUnprotectedPosition: false
  }
};

function deepMerge(base, override) {
  const out = { ...base };
  for (const [key, value] of Object.entries(override || {})) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = deepMerge(base[key] || {}, value);
    } else {
      out[key] = value;
    }
  }
  return out;
}

function stripJsonComments(text) {
  let out = '';
  let inString = false;
  let escaped = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];
    if (inString) {
      out += ch;
      if (escaped) {
        escaped = false;
      } else if (ch === '\\') {
        escaped = true;
      } else if (ch === '"') {
        inString = false;
      }
      continue;
    }
    if (ch === '"') {
      inString = true;
      out += ch;
      continue;
    }
    if (ch === '/' && next === '/') {
      while (i < text.length && text[i] !== '\n') i += 1;
      out += '\n';
      continue;
    }
    if (ch === '/' && next === '*') {
      i += 2;
      while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i += 1;
      i += 1;
      continue;
    }
    out += ch;
  }
  return out;
}

function readJsonConfig(filePath) {
  return JSON.parse(stripJsonComments(fs.readFileSync(filePath, 'utf8')));
}

export function loadConfig() {
  const localPath = path.join(ROOT, 'config.local.json');
  const examplePath = path.join(ROOT, 'config.example.json');
  let fileConfig = {};
  if (fs.existsSync(localPath)) {
    fileConfig = readJsonConfig(localPath);
  } else if (fs.existsSync(examplePath)) {
    fileConfig = readJsonConfig(examplePath);
  }

  const cfg = deepMerge(DEFAULT_CONFIG, fileConfig);
  return cfg;
}

export function saveMutableConfig(config) {
  const localPath = path.join(ROOT, 'config.local.json');
  fs.writeFileSync(localPath, JSON.stringify(config, null, 2) + '\n');
}
