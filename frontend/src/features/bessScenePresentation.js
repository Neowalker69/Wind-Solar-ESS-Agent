const HEALTH_LEVELS = new Set(["normal", "warning", "critical"]);
const HEALTH_RANK = Object.freeze({ normal: 0, warning: 1, critical: 2 });

function elevatedHealthLevel(current, candidate) {
  return HEALTH_RANK[candidate] > HEALTH_RANK[current] ? candidate : current;
}

export function bessHealthLevel(container, fallback = "normal") {
  const statusCode = container?.statusCode;
  const alarmSeverity = container?.alarmSeverity;
  let level = HEALTH_LEVELS.has(container?.severity) ? container.severity : fallback;

  if (alarmSeverity >= 700 || statusCode === 4) level = "critical";
  else if (alarmSeverity > 0 || statusCode === 0 || statusCode >= 3) level = "warning";
  else if (Number.isFinite(statusCode)) level = "normal";

  if (Number.isFinite(container?.soc)) {
    if (container.soc < 20) level = elevatedHealthLevel(level, "critical");
    else if (container.soc < 50) level = elevatedHealthLevel(level, "warning");
  }
  if (Number.isFinite(container?.temp)) {
    if (container.temp >= 50) level = elevatedHealthLevel(level, "critical");
    else if (container.temp >= 40) level = elevatedHealthLevel(level, "warning");
  }
  return level;
}

export function sourceAssetIdForSceneContainer(sceneContainerId) {
  const match = /^A-(\d{2})$/.exec(sceneContainerId || "");
  return match ? `BESS_A_${match[1]}` : sceneContainerId || "unknown";
}

export function bessScenePresentation(container) {
  const level = bessHealthLevel(container);
  return {
    assetId: container?.sourceAssetId || sourceAssetIdForSceneContainer(container?.id),
    level,
    statusLabel: container?.dataState === "stale" ? "数据过期" : null,
    soh: Number.isFinite(container?.soh) ? container.soh : null,
  };
}
