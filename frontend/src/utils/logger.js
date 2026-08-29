const DEV_ENABLED_LEVELS = new Set(["debug", "info", "warn", "error"]);
const PROD_ENABLED_LEVELS = new Set(["warn", "error"]);

function getRuntimeFlags() {
  const store = globalThis.__WIND_SUN_STORAGE_STORE__;
  const debugLogsEnabled = store?.getState?.().debugLogsEnabled;
  return {
    isDev: process.env.NODE_ENV !== 'production',
    debugLogsEnabled,
  };
}

function shouldLog(level) {
  const { isDev, debugLogsEnabled } = getRuntimeFlags();
  if (debugLogsEnabled === true) return true;
  if (debugLogsEnabled === false) return level === "warn" || level === "error";
  return isDev ? DEV_ENABLED_LEVELS.has(level) : PROD_ENABLED_LEVELS.has(level);
}

function emit(level, category, msg, data) {
  const entry = {
    ts: new Date().toISOString(),
    level,
    category,
    msg,
    data: data ?? null,
  };

  if (!shouldLog(level)) return entry;

  const method = level === "debug" ? "debug" : level === "info" ? "info" : level === "warn" ? "warn" : "error";
  console[method](`[${entry.ts}] [${entry.level.toUpperCase()}] [${entry.category}] ${entry.msg}`, entry.data ?? "");
  return entry;
}

export const logger = {
  debug: (category, msg, data) => emit("debug", category, msg, data),
  info: (category, msg, data) => emit("info", category, msg, data),
  warn: (category, msg, data) => emit("warn", category, msg, data),
  error: (category, msg, data) => emit("error", category, msg, data),
};
