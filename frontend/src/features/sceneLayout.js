export const CONTAINER_COUNT = 32;

export const BESS_RESERVE_BOUNDS = Object.freeze({
  minX: -62.5,
  maxX: 62.5,
  minZ: -80,
  maxZ: 80,
});

export const CONTAINER_LAYOUT = Object.freeze({
  rows: 8,
  columns: 4,
  gapX: 17.5,
  gapZ: 15.5,
  containerSize: [6.868, 3.756],
});

export const CONTAINER_MODEL = Object.freeze({
  scale: 2,
  center: Object.freeze([2.624, 1.479, -0.564]),
  normalizationOffset: Object.freeze([-2.624, 0, 0.564]),
  labelAnchorY: 7.2,
});

export const CONTAINER_OVERVIEW_MODEL = Object.freeze({
  center: Object.freeze([2.624, 1.479, -1.149]),
  normalizationOffset: Object.freeze([-2.624, 0, 1.149]),
});

export const CONTAINER_OVERVIEW_GROUPS = Object.freeze([
  "Shell",
  "Frame",
  "Doors",
  "HVAC",
  "Visible_Details",
]);

export const UHV_SCENE_OFFSET = Object.freeze([-155, 0, 30]);

export const SCENE_RENDER_POLICY = Object.freeze({
  realtimeShadows: false,
  hideUhvWhenFocused: false,
  focusShellMeshCount: 1,
  cameraNear: 0.5,
  cameraFar: 900,
});

export const UHV_LAYER_Y = Object.freeze({
  ground: 0,
  road: 0.025,
  pad: 0.05,
  boundary: 0.12,
  label: 0.3,
});

export const SOC_LABEL_UI = Object.freeze({
  fixedScreenSize: true,
  compactWidth: 132,
  standardWidth: 148,
  selectedWidth: 176,
});

export const WIND_LAYOUT = Object.freeze({
  scale: 2,
  rotorRadius: 10.4,
  pvMaxX: -9,
  xPositions: Object.freeze([8, 30, 52, 74]),
  zPositions: Object.freeze([92, 116, 140, 164]),
});

export const COOLING_SPEED_MULTIPLIER = 5;

export const COOLING_FAN_PIVOTS = Object.freeze({
  HVAC_FanRotor_1: Object.freeze([-0.575613, 1.182812, -0.669622]),
  HVAC_FanRotor_2: Object.freeze([-0.575613, 1.852812, -0.669622]),
});

export const COOLING_PROFILES = Object.freeze({
  low: Object.freeze({ rpm: 480 * COOLING_SPEED_MULTIPLIER, angularVelocity: 2.8 * COOLING_SPEED_MULTIPLIER, particleCount: 4, particleSpeed: 0.55 }),
  medium: Object.freeze({ rpm: 900 * COOLING_SPEED_MULTIPLIER, angularVelocity: 5.2 * COOLING_SPEED_MULTIPLIER, particleCount: 8, particleSpeed: 0.9 }),
  high: Object.freeze({ rpm: 1500 * COOLING_SPEED_MULTIPLIER, angularVelocity: 8.5 * COOLING_SPEED_MULTIPLIER, particleCount: 14, particleSpeed: 1.35 }),
});

const EXISTING_CONTAINER_DATA = [
  { severity: "normal", soc: 80, temp: 28.5, power: 320 },
  { severity: "normal", soc: 75, temp: 29.2, power: 305 },
  { severity: "critical", soc: 13, temp: 56.5, power: 0 },
  { severity: "normal", soc: 82, temp: 27.8, power: 318 },
  { severity: "normal", soc: 78, temp: 30.1, power: 310 },
  { severity: "normal", soc: 81, temp: 28.9, power: 322 },
  { severity: "warning", soc: 68, temp: 42.3, power: 240 },
  { severity: "normal", soc: 79, temp: 29.6, power: 308 },
  { severity: "normal", soc: 84, temp: 28.1, power: 325 },
  { severity: "normal", soc: 77, temp: 30.4, power: 312 },
];

const RACK_CENTERS = [
  [0.88, -0.735],
  [2.1, -0.735],
  [3.48, -0.735],
  [0.88, -1.67],
  [2.1, -1.67],
  [3.48, -1.67],
];

const PACKAGE_LAYER_COUNT = 8;
const PACKAGE_BASE_Y = 0.282;
const PACKAGE_LAYER_GAP = 0.3;

export const EQUIPMENT_ANCHORS = Object.freeze({
  floorY: 0.235,
  rackMaxX: 4.01,
  pcs: Object.freeze({
    position: Object.freeze([4.65, 0.317, -0.72]),
    scale: 0.82,
    modelBottomY: -0.1,
  }),
  cdu: Object.freeze({
    position: Object.freeze([5.55, 0.235, -1.54]),
    scale: 0.7,
    modelBottomY: 0,
  }),
});

export function uhvLayerForNode(name) {
  if (name === "SITE_GROUND") return { key: "ground", y: UHV_LAYER_Y.ground, order: 0, adjustY: true };
  if (/^ROAD_/.test(name)) return { key: "road", y: UHV_LAYER_Y.road, order: 1, adjustY: true };
  if (name === "BESS_RESERVE_PAD" || /^PAD_/.test(name)) {
    return { key: "pad", y: UHV_LAYER_Y.pad, order: 2, adjustY: true };
  }
  if (/^(BESS_RESERVE_BOUNDARY|PV_FIELD_BOUNDARY)_\d+$/.test(name)) {
    return { key: "boundary", y: UHV_LAYER_Y.boundary, order: 3, adjustY: false };
  }
  if (/^(LABEL_|AIS_LABEL_)/.test(name)) {
    return { key: "label", y: UHV_LAYER_Y.label, order: 4, adjustY: false };
  }
  return null;
}

export function isCoolingFanRotorNode(name) {
  return /^HVAC[_ ]FanRotor_\d+$/i.test(name);
}

export function coolingFanPivotForNode(name) {
  return COOLING_FAN_PIVOTS[name] || null;
}

export function containerSlotPosition(index) {
  const row = Math.floor(index / CONTAINER_LAYOUT.columns);
  const column = index % CONTAINER_LAYOUT.columns;
  return [
    (column - (CONTAINER_LAYOUT.columns - 1) / 2) * CONTAINER_LAYOUT.gapX,
    0.04,
    (row - (CONTAINER_LAYOUT.rows - 1) / 2) * CONTAINER_LAYOUT.gapZ,
  ];
}

export function createContainerFleet() {
  return Array.from({ length: CONTAINER_COUNT }, (_, index) => {
    const existing = EXISTING_CONTAINER_DATA[index];
    const generated = {
      severity: "normal",
      soc: 72 + ((index * 7) % 15),
      temp: +(27.4 + ((index * 13) % 31) / 10).toFixed(1),
      power: 286 + ((index * 17) % 42),
    };
    return {
      id: `A-${String(index + 1).padStart(2, "0")}`,
      ...(existing || generated),
    };
  });
}

export function createBatteryPackageSlots() {
  return RACK_CENTERS.flatMap(([x, z], rackIndex) =>
    Array.from({ length: PACKAGE_LAYER_COUNT }, (_, layerIndex) => ({
      rackId: `rack-${rackIndex + 1}`,
      logicalPackageIndex: layerIndex,
      position: [x, PACKAGE_BASE_Y + layerIndex * PACKAGE_LAYER_GAP, z],
      rotation: [0, 0, 0],
      scale: 0.75,
    })),
  );
}

export function batteryPackageSlotForLayer(layerIndex) {
  return createBatteryPackageSlots().find(
    ({ logicalPackageIndex }) => logicalPackageIndex === layerIndex,
  );
}

export function createWindTurbinePositions() {
  return WIND_LAYOUT.zPositions.flatMap((z) =>
    WIND_LAYOUT.xPositions.map((x) => [x, 0, z]),
  );
}

export function coolingLevelForContainer(container) {
  if (container?.dataState === "live" && Number.isFinite(container?.fanRpm)) {
    if (container.fanRpm >= 1500) return "high";
    if (container.fanRpm >= 900) return "medium";
    return "low";
  }
  if (container?.severity === "critical" || container?.temp >= 50) return "high";
  if (container?.severity === "warning" || container?.temp >= 40) return "medium";
  return "low";
}

export function fanAngularVelocityForContainer(container) {
  if (container?.dataState !== "live" || !Number.isFinite(container?.fanRpm)) return null;
  return Math.max(0, container.fanRpm) * Math.PI * 2 / 60;
}

export function containerLocalToWorld(slotPosition, localPosition) {
  return [
    slotPosition[0] + (localPosition[0] - CONTAINER_MODEL.center[0]) * CONTAINER_MODEL.scale,
    slotPosition[1] + localPosition[1] * CONTAINER_MODEL.scale,
    slotPosition[2] + (localPosition[2] - CONTAINER_MODEL.center[2]) * CONTAINER_MODEL.scale,
  ];
}

export function containerOverviewLocalToWorld(slotPosition, localPosition) {
  return [
    slotPosition[0] + (localPosition[0] - CONTAINER_OVERVIEW_MODEL.center[0]) * CONTAINER_MODEL.scale,
    slotPosition[1] + localPosition[1] * CONTAINER_MODEL.scale,
    slotPosition[2] + (localPosition[2] - CONTAINER_OVERVIEW_MODEL.center[2]) * CONTAINER_MODEL.scale,
  ];
}
