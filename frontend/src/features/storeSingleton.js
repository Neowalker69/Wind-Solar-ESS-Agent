const STORE_KEY = "__WIND_SUN_STORAGE_STORE__";

export function resolveWindSunStorageStore(createStore) {
  if (globalThis[STORE_KEY]) return globalThis[STORE_KEY];
  const store = createStore();
  globalThis[STORE_KEY] = store;
  return store;
}
