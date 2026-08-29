import React, { useRef, useMemo, useEffect, useLayoutEffect } from "react";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { useFrame, useThree } from "@react-three/fiber";
import {
  OrbitControls,
  Clone,
  useGLTF,
  Html,
  Text as DreiText,
  Sparkles,
  Float,
} from "@react-three/drei";
import { useStore, severityForTemp, tempColorScale, severityColor, clusterIdForDevice, packageMetricsForContainer } from "../store";
import { Icon, CameraFeed } from "./components";
import { resolveSocLabelLayout, SOC_LEVELS, lodForDistance } from "../features/digitalTwinAdapters";
import { bessScenePresentation } from "../features/bessScenePresentation";
import { withAssetCacheRevision } from "../features/staticAssetUrl";
import { dequantizeGeometry } from "../features/threeGeometry";
import {
  CONTAINER_MODEL,
  CONTAINER_OVERVIEW_GROUPS,
  CONTAINER_OVERVIEW_MODEL,
  COOLING_PROFILES,
  EQUIPMENT_ANCHORS,
  SCENE_RENDER_POLICY,
  SOC_LABEL_UI,
  UHV_SCENE_OFFSET,
  WIND_LAYOUT,
  batteryPackageSlotForLayer,
  containerLocalToWorld,
  containerOverviewLocalToWorld,
  containerSlotPosition,
  coolingFanPivotForNode,
  coolingLevelForContainer,
  createBatteryPackageSlots,
  createWindTurbinePositions,
  fanAngularVelocityForContainer,
  isCoolingFanRotorNode,
  uhvLayerForNode,
} from "../features/sceneLayout";
import { viewDefinitionForIndex } from "../../../apps/harness-control/src/workspace/twin-view-registry";

// ====================== GLB asset urls ======================
import essUrl from "../assets/3d_models/ESS_Container_DoorsClosed.glb?url";
import combinerUrl from "../assets/3d_models/Combiner_cabinet.glb?url";
import cduUrl from "../assets/3d_models/Liquid_CDU.glb?url";
import batteryPackUrl from "../assets/3d_models/battery_package.glb?url";
import uhvSubstationUrl from "../assets/3d_models/uhv_substation_structured.glb?url";

const DRACO_DECODER_PATH = "/draco/";
const SCENE_FONT_URL = "/fonts/ipag.ttf";
const essModelUrl = withAssetCacheRevision(essUrl);
const combinerModelUrl = withAssetCacheRevision(combinerUrl);
const cduModelUrl = withAssetCacheRevision(cduUrl);
const batteryPackModelUrl = withAssetCacheRevision(batteryPackUrl);
const uhvSubstationModelUrl = withAssetCacheRevision(uhvSubstationUrl);

useGLTF.setDecoderPath(DRACO_DECODER_PATH);
useGLTF.preload(essModelUrl, DRACO_DECODER_PATH);
useGLTF.preload(combinerModelUrl);
useGLTF.preload(cduModelUrl);
useGLTF.preload(batteryPackModelUrl);
useGLTF.preload(uhvSubstationModelUrl);

function Text({ children, ...props }) {
  return <DreiText {...props} font={SCENE_FONT_URL}>{children}</DreiText>;
}

const DISPLAY_FLOOR_NAMES = new Set(["Floor", "Ground", "BG_Plane", "ESS_M_Concrete"]);

function isDisplayFloor(object) {
  return DISPLAY_FLOOR_NAMES.has(object.name);
}

const DEFAULT_CAM = new THREE.Vector3(118, 92, 148);
const DEFAULT_TARGET = new THREE.Vector3(-54, 2, 2);
const CONTAINER_SCALE_VECTOR = new THREE.Vector3(
  CONTAINER_MODEL.scale,
  CONTAINER_MODEL.scale,
  CONTAINER_MODEL.scale,
);
const MODEL_NORMALIZATION_MATRIX = new THREE.Matrix4().makeTranslation(
  ...CONTAINER_OVERVIEW_MODEL.normalizationOffset,
);
const FAN_AXIS = new THREE.Vector3(1, 0, 0);

function normalizedModelGeometry(object) {
  return dequantizeGeometry(object.geometry)
    .applyMatrix4(object.matrixWorld)
    .applyMatrix4(MODEL_NORMALIZATION_MATRIX);
}

function meshesFromModelGroups(scene, groupNames) {
  const modelRoot = scene.getObjectByName("ESS_Container_Appearance_BatteryDoorsClosed");
  const meshes = [];
  modelRoot?.children
    .filter((child) => groupNames.includes(child.name))
    .forEach((group) => {
      group.traverse((object) => {
        if (object.isMesh) meshes.push(object);
      });
    });
  return meshes;
}

function buildOverviewParts(scene) {
  const modelRoot = scene.getObjectByName("ESS_Container_Appearance_BatteryDoorsClosed");
  if (!modelRoot) return [];

  scene.updateMatrixWorld(true);
  const inverseRootMatrix = modelRoot.matrixWorld.clone().invert();
  const geometriesByMaterial = new Map();

  modelRoot?.children
    .filter((child) => CONTAINER_OVERVIEW_GROUPS.includes(child.name))
    .forEach((group) => group.traverse((object) => {
      if (!object.isMesh || isCoolingFanRotorNode(object.name)) return;
      const material = Array.isArray(object.material) ? object.material[0] : object.material;
      if (!material) return;
      const relativeMatrix = new THREE.Matrix4().multiplyMatrices(
        inverseRootMatrix,
        object.matrixWorld,
      );
      const geometry = dequantizeGeometry(object.geometry)
        .applyMatrix4(relativeMatrix)
        .applyMatrix4(MODEL_NORMALIZATION_MATRIX);
      const entry = geometriesByMaterial.get(material.uuid) || {
        material,
        geometries: [],
        names: [],
      };
      entry.geometries.push(geometry);
      entry.names.push(object.name);
      geometriesByMaterial.set(material.uuid, entry);
    }));

  return [...geometriesByMaterial.values()].map(({ material, geometries, names }) => {
    const geometry = mergeGeometries(geometries, false);
    geometries.forEach((item) => item.dispose());
    if (!geometry) {
      throw new Error(`Unable to merge ESS overview geometry for material ${material.name}`);
    }
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    const clonedMaterial = material.clone();
    clonedMaterial.emissive?.set("#000000");
    clonedMaterial.emissiveIntensity = 0;
    return {
      key: material.uuid,
      geometry,
      material: clonedMaterial,
      castShadow: names.some((name) => /whitepaint|shell|body|panel|frame/i.test(
        `${name} ${material.name || ""}`,
      )),
    };
  });
}

function packageSlot(index) {
  const slot = batteryPackageSlotForLayer(index);
  return {
    position: slot.position,
    rotationY: 0,
    rowSign: -1,
  };
}

function containerCapacityKwh(container) {
  const index = Number(container?.id?.split("-")[1] || 0);
  return 3100 + index * 9;
}


// ====================== Emissive tinting helper ======================
// Applies a tint to all meshes of a cloned model without using transparency for dimming.
function useTintedClone(scene, { color, intensity = 0, dim = false, castShadow = true }) {
  const cloned = useMemo(() => scene.clone(true), [scene]);
  useLayoutEffect(() => {
    cloned.traverse((o) => {
      if (!o.isMesh) return;
      if (isDisplayFloor(o)) {
        o.visible = false;
        return;
      }
      o.castShadow = castShadow && /shell|white|body|case|cabinet/i.test(`${o.name} ${o.material?.name || ""}`);
      o.receiveShadow = true;
      // Clone material so each instance is independent.
      if (Array.isArray(o.material)) {
        o.material = o.material.map((m) => m.clone());
      } else if (o.material) {
        o.material = o.material.clone();
      }
    });
  }, [castShadow, cloned]);

  useLayoutEffect(() => {
    cloned.traverse((o) => {
      if (!o.isMesh || !o.material) return;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m) => {
        if (m.color) {
          if (!m.userData.baseColor) m.userData.baseColor = m.color.clone();
          m.color
            .copy(m.userData.baseColor)
            .lerp(new THREE.Color(color || "#ffffff"), dim ? 0.06 : 0.16)
            .multiplyScalar(dim ? 0.38 : 1);
        }
        if (m.emissive) {
          m.emissive.set(color || "#000000");
          m.emissiveIntensity = dim ? intensity * 0.2 : intensity;
        }
      });
    });
  }, [cloned, color, intensity, dim]);

  return cloned;
}

function UhvSubstationScene({ visible }) {
  const { scene } = useGLTF(uhvSubstationModelUrl);
  const cloned = useMemo(() => scene.clone(true), [scene]);

  useLayoutEffect(() => {
    cloned.traverse((object) => {
      if (!object.isMesh) return;
      object.receiveShadow = false;
      object.castShadow = false;
      const layer = uhvLayerForNode(object.name);
      if (!layer) return;
      if (layer.adjustY) object.position.y = layer.y;
      object.material = Array.isArray(object.material)
        ? object.material.map((material) => material.clone())
        : object.material.clone();
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((material) => {
        material.polygonOffset = true;
        material.polygonOffsetFactor = -layer.order;
        material.polygonOffsetUnits = -layer.order;
        if (material.transparent && layer.key !== "boundary") {
          material.depthWrite = false;
        }
      });
      object.renderOrder = layer.order;
    });
  }, [cloned]);

  return (
    <group position={UHV_SCENE_OFFSET} visible={visible}>
      <primitive object={cloned} />
    </group>
  );
}

function containerVisualState(container, index, {
  activeView,
  selectedDevice,
  hoverDevice,
  tempRange,
}) {
  const definition = viewDefinitionForIndex(activeView);
  const selected = definition.sceneProfile === "asset" && clusterIdForDevice(selectedDevice) === container.id;
  const hovered = hoverDevice === container.id;
  const heatmap = definition.sceneProfile === "thermal";
  const inRange = container.temp >= tempRange[0] && container.temp <= tempRange[1];
  const containerFocusActive = definition.sceneProfile === "asset" && Boolean(clusterIdForDevice(selectedDevice));
  const dim = (heatmap && !inRange) || (containerFocusActive && !selected);
  const level = bessScenePresentation(container).level;
  let color = heatmap ? tempColorScale(container.temp) : severityColor(level);
  if (selected) color = "#00d4ff";
  else if (hovered) color = "#7dd3fc";

  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3(...containerSlotPosition(index));
  const rotation = new THREE.Quaternion();
  const scale = new THREE.Vector3(
    CONTAINER_MODEL.scale,
    CONTAINER_MODEL.scale,
    CONTAINER_MODEL.scale,
  );
  if (selected) {
    scale.setScalar(0);
  } else if (hovered) {
    position.y += 0.36;
  }
  matrix.compose(position, rotation, scale);

  const instanceColor = new THREE.Color(color);
  if (!heatmap && !selected && !hovered) instanceColor.lerp(new THREE.Color("#ffffff"), 0.48);
  if (dim) instanceColor.multiplyScalar(0.2);
  return { matrix, instanceColor, selected, hovered, heatmap, inRange, dim, level };
}

// ====================== Storage Containers (shared GLB parts, instanced across all cabinets) ======================
function StorageContainerInstances({ containers }) {
  const { scene } = useGLTF(essModelUrl, DRACO_DECODER_PATH);
  const selectedDevice = useStore((s) => s.selectedDevice);
  const hoverDevice = useStore((s) => s.hoverDevice);
  const activeView = useStore((s) => s.activeView);
  const tempRange = useStore((s) => s.tempRange);
  const setSelectedDevice = useStore((s) => s.setSelectedDevice);
  const setHoverDevice = useStore((s) => s.setHoverDevice);
  const meshRefs = useRef([]);
  const parts = useMemo(() => buildOverviewParts(scene), [scene]);

  const visualStates = useMemo(
    () => containers.map((container, index) => containerVisualState(container, index, {
      activeView,
      selectedDevice,
      hoverDevice,
      tempRange,
    })),
    [activeView, containers, hoverDevice, selectedDevice, tempRange]
  );

  useLayoutEffect(() => {
    meshRefs.current.forEach((mesh) => {
      if (!mesh) return;
      visualStates.forEach(({ matrix, instanceColor }, index) => {
        mesh.setMatrixAt(index, matrix);
        mesh.setColorAt(index, instanceColor);
      });
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.computeBoundingSphere();
    });
  }, [parts, visualStates]);

  const selectInstance = (event) => {
    event.stopPropagation();
    const container = containers[event.instanceId];
    if (container) setSelectedDevice(container.id);
  };
  const hoverInstance = (event) => {
    event.stopPropagation();
    const container = containers[event.instanceId];
    if (!container) return;
    setHoverDevice(container.id);
    document.body.style.cursor = "pointer";
  };
  const leaveInstances = (event) => {
    event.stopPropagation();
    setHoverDevice(null);
    document.body.style.cursor = "auto";
  };

  return (
    <group>
      {parts.map((part, partIndex) => (
        <instancedMesh
          key={part.key}
          ref={(mesh) => { meshRefs.current[partIndex] = mesh; }}
          args={[part.geometry, part.material, containers.length]}
          castShadow={part.castShadow}
          receiveShadow
          onClick={selectInstance}
          onPointerOver={hoverInstance}
          onPointerOut={leaveInstances}
        />
      ))}
    </group>
  );
}

function CoolingFanRotors({ containers, levelOverride }) {
  const { scene } = useGLTF(essModelUrl, DRACO_DECODER_PATH);
  const hoverDevice = useStore((state) => state.hoverDevice);
  const rotorRefs = useRef([]);
  const rotorParts = useMemo(() => {
    scene.updateMatrixWorld(true);
    const result = [];
    meshesFromModelGroups(scene, ["HVAC"]).forEach((object) => {
      if (!isCoolingFanRotorNode(object.name)) return;
      const geometry = normalizedModelGeometry(object);
      const modelPivot = coolingFanPivotForNode(object.name);
      if (!modelPivot) return;
      const pivot = new THREE.Vector3(...modelPivot).applyMatrix4(MODEL_NORMALIZATION_MATRIX);
      geometry.translate(-pivot.x, -pivot.y, -pivot.z);
      const material = object.material.clone();
      material.color?.lerp(new THREE.Color("#d7f5ff"), 0.38);
      material.emissive?.set("#0e7490");
      material.emissiveIntensity = 0.22;
      result.push({
        name: object.name,
        geometry,
        material,
        pivot,
      });
    });
    return result;
  }, [scene]);

  useFrame(({ clock }) => {
    const elapsed = clock.getElapsedTime();
    rotorRefs.current.forEach((mesh, partIndex) => {
      const part = rotorParts[partIndex];
      if (!mesh || !part) return;
      containers.forEach((container, index) => {
        const level = levelOverride === "auto"
          ? coolingLevelForContainer(container)
          : levelOverride;
        const profile = COOLING_PROFILES[level];
        const telemetryAngularVelocity = levelOverride === "auto"
          ? fanAngularVelocityForContainer(container)
          : null;
        const slot = containerSlotPosition(index);
        const position = new THREE.Vector3(
          slot[0],
          slot[1] + (hoverDevice === container.id ? 0.36 : 0),
          slot[2],
        );
        const base = new THREE.Matrix4().compose(
          position,
          new THREE.Quaternion(),
          new THREE.Vector3(
            CONTAINER_MODEL.scale,
            CONTAINER_MODEL.scale,
            CONTAINER_MODEL.scale,
          ),
        );
        const rotation = new THREE.Matrix4().makeRotationAxis(
          FAN_AXIS,
          elapsed * (telemetryAngularVelocity ?? profile.angularVelocity),
        );
        const matrix = base
          .multiply(new THREE.Matrix4().makeTranslation(...part.pivot.toArray()))
          .multiply(rotation);
        mesh.setMatrixAt(index, matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
    });
  });

  return rotorParts.map((part, index) => (
    <instancedMesh
      key={part.name}
      ref={(mesh) => { rotorRefs.current[index] = mesh; }}
      args={[part.geometry, part.material, containers.length]}
      frustumCulled={false}
    />
  ));
}

function CoolingAirflow({ containers, levelOverride }) {
  const pointsRef = useRef();
  const particles = useMemo(() => containers.flatMap((container, containerIndex) => {
    const level = levelOverride === "auto"
      ? coolingLevelForContainer(container)
      : levelOverride;
    const profile = COOLING_PROFILES[level];
    return Array.from({ length: profile.particleCount }, (_, particleIndex) => ({
      containerIndex,
      speed: profile.particleSpeed,
      phase: particleIndex / profile.particleCount,
      fanOffsetY: particleIndex % 2 === 0 ? -0.34 : 0.34,
      lateralOffset: ((particleIndex * 17) % 9 - 4) * 0.035,
    }));
  }), [containers, levelOverride]);
  const positions = useMemo(
    () => new Float32Array(particles.length * 3),
    [particles.length],
  );

  useFrame(({ clock }) => {
    const elapsed = clock.getElapsedTime();
    particles.forEach((particle, index) => {
      const slot = containerSlotPosition(particle.containerIndex);
      const progress = (particle.phase + elapsed * particle.speed * 0.16) % 1;
      const outlet = containerOverviewLocalToWorld(slot, [-0.575613, 1.517812 + particle.fanOffsetY, -0.669622]);
      positions[index * 3] = outlet[0] - progress * 4.8;
      positions[index * 3 + 1] = outlet[1] + particle.lateralOffset;
      positions[index * 3 + 2] = outlet[2] + particle.lateralOffset * 1.6;
    });
    if (pointsRef.current) {
      pointsRef.current.geometry.attributes.position.needsUpdate = true;
    }
  });

  return (
    <points ref={pointsRef} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        color="#67e8f9"
        size={0.2}
        sizeAttenuation
        transparent
        opacity={0.72}
        depthWrite={false}
      />
    </points>
  );
}

function CoolingSystem({ containers, levelOverride }) {
  return (
    <group>
      <CoolingFanRotors containers={containers} levelOverride={levelOverride} />
      <CoolingAirflow containers={containers} levelOverride={levelOverride} />
    </group>
  );
}

function SocFloatingLabel({ container, selected, hovered, dimmed, registerLabel }) {
  const elementRef = useRef(null);
  const anchorRef = useRef(null);
  const camera = useThree((state) => state.camera);
  const setSelectedDevice = useStore((state) => state.setSelectedDevice);
  const setHoverDevice = useStore((state) => state.setHoverDevice);
  const worldPosition = useMemo(() => new THREE.Vector3(), []);
  const information = bessScenePresentation(container);
  const level = information.level;
  const presentation = SOC_LEVELS[level];
  const statusLabel = information.statusLabel || presentation.label;
  const flow = container.power > 0 ? "discharging" : container.power < 0 ? "charging" : "standby";

  useEffect(() => {
    registerLabel(container.id, { anchorRef, elementRef, container, selected, hovered, level });
    return () => registerLabel(container.id, null);
  }, [container, hovered, level, registerLabel, selected]);

  useFrame(() => {
    if (!anchorRef.current || !elementRef.current) return;
    anchorRef.current.getWorldPosition(worldPosition);
    const distanceLod = lodForDistance(camera.position.distanceTo(worldPosition));
    elementRef.current.dataset.lod = distanceLod === "detail" && !selected && !hovered ? "standard" : distanceLod;
  });

  return (
    <group>
      <mesh position={[0, CONTAINER_MODEL.labelAnchorY / 2, 0]}>
        <cylinderGeometry args={[0.018, 0.018, CONTAINER_MODEL.labelAnchorY, 8]} />
        <meshBasicMaterial color={presentation.color} transparent opacity={0.62} />
      </mesh>
      <group ref={anchorRef} position={[0, CONTAINER_MODEL.labelAnchorY, 0]}>
        <Html center zIndexRange={[24, 0]}>
          <button
            ref={elementRef}
            type="button"
            className={`soc-floating-label ${level} ${selected ? "selected" : ""} ${hovered ? "hovered" : ""} ${dimmed ? "dimmed" : ""}`}
            style={{
              "--soc-color": presentation.color,
              "--soc-gradient": presentation.gradient,
              "--soc-value": `${Math.max(0, Math.min(100, container.soc))}%`,
              "--soc-label-width": `${selected ? SOC_LABEL_UI.selectedWidth : SOC_LABEL_UI.standardWidth}px`,
            }}
            aria-label={`${information.assetId}，SOC ${container.soc}%，${statusLabel}`}
            onClick={(event) => { event.stopPropagation(); setSelectedDevice(container.id); }}
            onPointerEnter={() => setHoverDevice(container.id)}
            onPointerLeave={() => setHoverDevice(null)}
          >
            <span className="soc-label-primary"><b>{information.assetId}</b><strong>{container.soc.toFixed(0)}<small>%</small></strong></span>
            <span className="soc-energy-track"><i data-flow={flow} /></span>
            <span className="soc-label-status"><em>{statusLabel}</em><span>{flow === "charging" ? "充电中" : flow === "discharging" ? "放电中" : "待机"}</span></span>
            <span className="soc-label-details"><span>SOH {Number.isFinite(information.soh) ? `${information.soh.toFixed(1)}%` : "--"}</span><span>{container.power.toFixed(0)} kW</span><span>{container.temp.toFixed(1)}℃</span></span>
          </button>
        </Html>
      </group>
    </group>
  );
}

function StorageContainerOverlays({ containers }) {
  const selectedDevice = useStore((s) => s.selectedDevice);
  const hoverDevice = useStore((s) => s.hoverDevice);
  const activeView = useStore((s) => s.activeView);
  const tempRange = useStore((s) => s.tempRange);
  const labelsOn = useStore((s) => s.layers.labels);
  const selectedClusterId = clusterIdForDevice(selectedDevice);
  const labelRegistryRef = useRef(new Map());
  const layoutClockRef = useRef(0);
  const clusterElementRef = useRef(null);
  const clusterExpandedUntilRef = useRef(0);
  const worldPosition = useMemo(() => new THREE.Vector3(), []);
  const projected = useMemo(() => new THREE.Vector3(), []);
  const registerLabel = useMemo(() => (id, entry) => {
    if (entry) labelRegistryRef.current.set(id, entry);
    else labelRegistryRef.current.delete(id);
  }, []);

  useFrame(({ camera, size }, delta) => {
    layoutClockRef.current += delta;
    if (layoutClockRef.current < 0.15) return;
    layoutClockRef.current = 0;
    const candidates = [];
    for (const [id, entry] of labelRegistryRef.current) {
      const anchor = entry.anchorRef.current;
      const element = entry.elementRef.current;
      if (!anchor || !element) continue;
      anchor.getWorldPosition(worldPosition);
      projected.copy(worldPosition).project(camera);
      candidates.push({
        id,
        x: (projected.x * 0.5 + 0.5) * size.width,
        y: (-projected.y * 0.5 + 0.5) * size.height,
        width: element.offsetWidth || SOC_LABEL_UI.standardWidth,
        height: element.offsetHeight || 62,
        distance: camera.position.distanceTo(worldPosition),
        level: entry.level,
        selected: entry.selected,
        hovered: entry.hovered,
        soc: entry.container.soc,
      });
    }
    const expanded = Date.now() < clusterExpandedUntilRef.current;
    const layout = resolveSocLabelLayout(candidates, { clusterDistance: expanded ? Number.POSITIVE_INFINITY : 95 });
    for (const [id, entry] of labelRegistryRef.current) {
      const element = entry.elementRef.current;
      const placement = layout.items.get(id);
      if (!element || !placement) continue;
      element.style.visibility = placement.visible ? "visible" : "hidden";
      element.style.translate = `${placement.offsetX}px ${placement.offsetY}px`;
    }
    if (clusterElementRef.current) {
      clusterElementRef.current.style.visibility = layout.cluster ? "visible" : "hidden";
    }
  });

  const averageSoc = Math.round(containers.reduce((sum, container) => sum + container.soc, 0) / Math.max(1, containers.length));
  const alarmCount = containers.filter((container) => ["warning", "critical"].includes(bessScenePresentation(container).level)).length;
  return <>
    {containers.map((container, index) => {
    const visual = containerVisualState(container, index, {
      activeView,
      selectedDevice,
      hoverDevice,
      tempRange,
    });
    const isCritical = severityForTemp(container.temp) === "critical";
    return (
      <group key={container.id} position={containerSlotPosition(index)}>
      {visual.selected && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
          <ringGeometry args={[6.4, 7.0, 48]} />
          <meshBasicMaterial
            color="#00d4ff"
            transparent
            opacity={0.9}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}

      {visual.heatmap && isCritical && (
        <Sparkles
          position={[0, 7.2, 0]}
          count={40}
          scale={[6, 8, 6]}
          size={6}
          speed={0.6}
          color={"#ef4444"}
          opacity={0.9}
        />
      )}

      {labelsOn && (!selectedClusterId || visual.selected || visual.hovered) && (
        <SocFloatingLabel
          container={container}
          selected={visual.selected}
          hovered={visual.hovered}
          dimmed={visual.dim}
          registerLabel={registerLabel}
        />
      )}
    </group>
    );
    })}
    {labelsOn && <group position={[0, 11, 0]}><Html center distanceFactor={34} zIndexRange={[26, 0]}><button ref={clusterElementRef} type="button" className="soc-cluster-label" style={{ visibility: "hidden" }} onClick={() => { clusterExpandedUntilRef.current = Date.now() + 10_000; }}>储能区 <b>{averageSoc}%</b><span>{containers.length} 台 · {alarmCount} 告警</span></button></Html></group>}
  </>;
}

// ====================== Generic prop model ======================
function PropModel({ url, position, rotation = [0, 0, 0], scale = 1, tint = "#0b2233", intensity = 0.12, dim = false, castShadow = true }) {
  const { scene } = useGLTF(url);
  const cloned = useTintedClone(scene, { color: tint, intensity: dim ? intensity * 0.45 : intensity, dim, castShadow });
  return (
    <group position={position} rotation={rotation} scale={scale}>
      <Clone object={cloned} />
    </group>
  );
}

// ====================== Wind turbine (primitives) ======================
function WindTurbine({ position, scale = 1, speed = 1 }) {
  const bladesRef = useRef();
  useFrame((_, dt) => {
    if (bladesRef.current) bladesRef.current.rotation.z += dt * speed;
  });
  return (
    <group position={position} scale={scale}>
      {/* tower */}
      <mesh position={[0, 6, 0]} castShadow>
        <cylinderGeometry args={[0.18, 0.32, 12, 12]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.6} roughness={0.4} />
      </mesh>
      {/* nacelle + blades */}
      <group position={[0, 12, 0.4]}>
        <mesh castShadow>
          <boxGeometry args={[0.6, 0.5, 1.4]} />
          <meshStandardMaterial color="#e2e8f0" metalness={0.5} roughness={0.5} />
        </mesh>
        <group ref={bladesRef} position={[0, 0, 0.8]}>
          {[0, 120, 240].map((a) => (
            <mesh key={a} rotation={[0, 0, (a * Math.PI) / 180]} position={[0, 0, 0]} castShadow>
              <mesh position={[0, 2.6, 0]}>
                <boxGeometry args={[0.16, 5.2, 0.05]} />
                <meshStandardMaterial color="#f1f5f9" metalness={0.2} roughness={0.6} />
              </mesh>
            </mesh>
          ))}
          <mesh>
            <sphereGeometry args={[0.28, 16, 16]} />
            <meshStandardMaterial color="#94a3b8" metalness={0.6} roughness={0.3} />
          </mesh>
        </group>
      </group>
    </group>
  );
}

// ====================== Camera reset controller ======================
function SceneControls() {
  const controlsRef = useRef();
  const resetCameraNonce = useStore((s) => s.resetCameraNonce);
  const cameraPreset = useStore((s) => s.cameraPreset);
  const markCameraUserControlled = useStore((s) => s.markCameraUserControlled);
  const containers = useStore((s) => s.containers);
  const activeView = useStore((s) => s.activeView);
  const selectedDevice = useStore((s) => s.selectedDevice);
  const selectedPackageIndex = useStore((s) => s.selectedPackageIndex);
  const desiredPositionRef = useRef(DEFAULT_CAM.clone());
  const desiredTargetRef = useRef(DEFAULT_TARGET.clone());
  const transitioningRef = useRef(false);
  const hadContainerFocusRef = useRef(false);

  const applyPreset = (preset) => {
    desiredPositionRef.current.copy(preset?.pos ? new THREE.Vector3(...preset.pos) : DEFAULT_CAM.clone());
    desiredTargetRef.current.copy(preset?.target ? new THREE.Vector3(...preset.target) : DEFAULT_TARGET.clone());
    transitioningRef.current = true;
  };

  useEffect(() => {
    applyPreset(cameraPreset);
  }, [resetCameraNonce, cameraPreset]);

  useEffect(() => {
    const selectedClusterId = viewDefinitionForIndex(activeView).sceneProfile === "asset" ? clusterIdForDevice(selectedDevice) : null;
    const containerIndex = containers.findIndex((container) => container.id === selectedClusterId);
    if (containerIndex < 0) {
      if (hadContainerFocusRef.current) applyPreset(null);
      hadContainerFocusRef.current = false;
      return;
    }
    hadContainerFocusRef.current = true;

    const baseSlot = containerSlotPosition(containerIndex);
    const slot = selectedPackageIndex == null ? null : packageSlot(selectedPackageIndex);
    const target = slot
      ? containerLocalToWorld(baseSlot, [
        slot.position[0],
        slot.position[1] + 0.22,
        slot.position[2],
      ])
      : containerLocalToWorld(baseSlot, CONTAINER_MODEL.center);
    const side = slot?.rowSign || 1;
    const pos = slot
      ? [target[0] + 2.4, target[1] + 2.2, target[2] + side * 4.0]
      : [target[0] + 21, target[1] + 7.4, target[2] + 14.4];

    applyPreset({ pos, target });
  }, [activeView, containers, selectedDevice, selectedPackageIndex]);

  const containerFocusActive = viewDefinitionForIndex(activeView).sceneProfile === "asset" && Boolean(clusterIdForDevice(selectedDevice));

  useFrame((_, dt) => {
    const c = controlsRef.current;
    if (!c || !transitioningRef.current) return;
    const posLerp = 1 - Math.exp(-dt * 3.5);
    const targetLerp = 1 - Math.exp(-dt * 4.2);
    c.object.position.lerp(desiredPositionRef.current, posLerp);
    c.target.lerp(desiredTargetRef.current, targetLerp);
    c.update();
    if (
      c.object.position.distanceToSquared(desiredPositionRef.current) < 0.0001 &&
      c.target.distanceToSquared(desiredTargetRef.current) < 0.0001
    ) {
      c.object.position.copy(desiredPositionRef.current);
      c.target.copy(desiredTargetRef.current);
      c.update();
      transitioningRef.current = false;
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={containerFocusActive ? 2.4 : 8}
      maxDistance={containerFocusActive ? 56 : 420}
      minPolarAngle={0.15}
      maxPolarAngle={Math.PI / 2.15}
      target={DEFAULT_TARGET}
      onStart={() => {
        transitioningRef.current = false;
        markCameraUserControlled();
      }}
    />
  );
}

function InstancedGLBParts({ url, transforms, castShadow = false, instanceColors = null, onInstanceClick = null }) {
  const { scene } = useGLTF(url);
  const meshRefs = useRef([]);
  const parts = useMemo(() => {
    scene.updateMatrixWorld(true);
    const result = [];
    scene.traverse((object) => {
      if (!object.isMesh || isDisplayFloor(object)) return;
      result.push({
        name: object.name,
        geometry: object.geometry.clone().applyMatrix4(object.matrixWorld),
        material: object.material.clone(),
      });
    });
    return result;
  }, [scene]);
  const matrices = useMemo(() => transforms.map((transform) => {
    const position = new THREE.Vector3(...transform.position);
    const rotation = new THREE.Quaternion().setFromEuler(new THREE.Euler(...(transform.rotation || [0, 0, 0])));
    const scaleValue = transform.scale ?? 1;
    const scale = Array.isArray(scaleValue)
      ? new THREE.Vector3(...scaleValue)
      : new THREE.Vector3(scaleValue, scaleValue, scaleValue);
    return new THREE.Matrix4().compose(position, rotation, scale);
  }), [transforms]);

  useLayoutEffect(() => {
    meshRefs.current.forEach((mesh) => {
      if (!mesh) return;
      matrices.forEach((matrix, index) => {
        mesh.setMatrixAt(index, matrix);
        if (instanceColors?.[index]) mesh.setColorAt(index, instanceColors[index]);
      });
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.computeBoundingSphere();
    });
  }, [instanceColors, matrices, parts]);

  return parts.map((part, partIndex) => (
    <instancedMesh
      key={`${url}-${part.name}`}
      ref={(mesh) => { meshRefs.current[partIndex] = mesh; }}
      args={[part.geometry, part.material, transforms.length]}
      castShadow={castShadow}
      receiveShadow
      onClick={onInstanceClick ? (event) => {
        event.stopPropagation();
        onInstanceClick(event.instanceId);
      } : undefined}
    />
  ));
}

function XRayContainer({ position }) {
  const groupRef = useRef();

  useFrame((_, dt) => {
    const alpha = 1 - Math.exp(-dt * 4.5);
    if (groupRef.current) groupRef.current.scale.lerp(CONTAINER_SCALE_VECTOR, alpha);
  });

  return (
    <group ref={groupRef} position={position} scale={CONTAINER_MODEL.scale * 0.96}>
      <mesh position={[0, CONTAINER_MODEL.center[1], 0]} renderOrder={2}>
        <boxGeometry args={[6.868, 2.958, 3.756]} />
        <meshBasicMaterial
          color="#bdefff"
          transparent
          opacity={0.085}
          depthWrite={false}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
}

function RackFrame({ pack, selected }) {
  const slot = packageSlot(pack.index);
  const fanZ = slot.rowSign * 1.34;
  const fanLocalZ = fanZ - slot.position[2];
  const fanColor = selected ? "#00d4ff" : severityColor(pack.severity);

  return (
    <group position={[slot.position[0], 0, slot.position[2]]}>
      <mesh position={[0, 0.92, 0]}>
        <boxGeometry args={[0.72, 1.56, 0.54]} />
        <meshStandardMaterial color="#0b1220" metalness={0.45} roughness={0.5} transparent opacity={0.28} />
      </mesh>
      <mesh position={[0, 1.74, 0]}>
        <boxGeometry args={[0.82, 0.08, 0.6]} />
        <meshStandardMaterial color={selected ? "#164e63" : "#111827"} metalness={0.5} roughness={0.36} />
      </mesh>
      <mesh position={[0, 0.14, 0]}>
        <boxGeometry args={[0.82, 0.1, 0.6]} />
        <meshStandardMaterial color="#020617" metalness={0.6} roughness={0.42} />
      </mesh>
      {[-0.28, 0.28].map((x) => (
        <mesh key={x} position={[x, 0.94, slot.rowSign * 0.29]}>
          <boxGeometry args={[0.035, 1.48, 0.045]} />
          <meshStandardMaterial color={selected ? "#0891b2" : "#1f2937"} metalness={0.55} roughness={0.35} />
        </mesh>
      ))}
      {[0.45, 0.92, 1.38].map((y) => (
        <mesh key={y} position={[0, y, slot.rowSign * 0.29]}>
          <boxGeometry args={[0.64, 0.022, 0.04]} />
          <meshStandardMaterial color="#334155" metalness={0.45} roughness={0.45} />
        </mesh>
      ))}
      {[0.72, 1.18].map((y, fanIndex) => (
        <group key={fanIndex} position={[0, y, fanLocalZ]} rotation={[0, 0, fanIndex * 0.4]}>
          <mesh>
            <circleGeometry args={[0.14, 24]} />
            <meshStandardMaterial color="#020617" metalness={0.65} roughness={0.35} />
          </mesh>
          <mesh>
            <ringGeometry args={[0.1, 0.16, 28]} />
            <meshStandardMaterial color={fanColor} emissive={fanColor} emissiveIntensity={selected ? 0.45 : 0.18} transparent opacity={0.86} />
          </mesh>
          {[0, 1, 2].map((blade) => (
            <mesh key={blade} rotation={[0, 0, blade * (Math.PI * 2 / 3)]}>
              <boxGeometry args={[0.18, 0.026, 0.012]} />
              <meshStandardMaterial color="#94a3b8" metalness={0.4} roughness={0.42} />
            </mesh>
          ))}
        </group>
      ))}
      {[0.72, 1.18].map((y) => (
        <mesh key={y} position={[0, y, fanLocalZ + slot.rowSign * 0.18]} rotation={[slot.rowSign > 0 ? -Math.PI / 2 : Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.065, 0.26, 18]} />
          <meshStandardMaterial color={fanColor} emissive={fanColor} emissiveIntensity={0.22} transparent opacity={0.38} />
        </mesh>
      ))}
      <Text
        position={[0, 1.92, 0]}
        rotation={[0, slot.rowSign < 0 ? 0 : Math.PI, 0]}
        fontSize={0.12}
        color={selected ? "#67e8f9" : "#94a3b8"}
        anchorX="center"
      >
        P{String(pack.index + 1).padStart(2, "0")}
      </Text>
    </group>
  );
}

function ContainerInterior({ container, index }) {
  const selectedPackageIndex = useStore((s) => s.selectedPackageIndex);
  const setSelectedPackageIndex = useStore((s) => s.setSelectedPackageIndex);
  const setSelectedDevice = useStore((s) => s.setSelectedDevice);
  const rootRef = useRef();
  const packages = useMemo(() => packageMetricsForContainer(container), [container]);
  const packageTransforms = useMemo(() => createBatteryPackageSlots().map((slot) => {
    return {
      rackIndex: slot.logicalPackageIndex,
      position: slot.position,
      rotation: slot.rotation,
      scale: slot.scale,
    };
  }), []);
  const packageColors = useMemo(() => packageTransforms.map((transform) => {
    const pkg = packages[transform.rackIndex];
    return new THREE.Color(pkg.index === selectedPackageIndex ? "#00d4ff" : severityColor(pkg.severity));
  }), [packageTransforms, packages, selectedPackageIndex]);
  useFrame((_, dt) => {
    if (!rootRef.current) return;
    const alpha = 1 - Math.exp(-dt * 4.8);
    rootRef.current.scale.lerp(CONTAINER_SCALE_VECTOR, alpha);
  });

  return (
    <group ref={rootRef} position={containerSlotPosition(index)} scale={CONTAINER_MODEL.scale * 0.86}>
      <group position={CONTAINER_MODEL.normalizationOffset}>
        <InstancedGLBParts
          url={batteryPackModelUrl}
          transforms={packageTransforms}
          instanceColors={packageColors}
          onInstanceClick={(instanceIndex) => {
            const packageIndex = packageTransforms[instanceIndex]?.rackIndex ?? instanceIndex;
            setSelectedPackageIndex(packageIndex);
            setSelectedDevice(packages[packageIndex].id);
          }}
        />
        <PropModel url={combinerModelUrl} {...EQUIPMENT_ANCHORS.pcs} tint="#8b5cf6" intensity={0.28} castShadow={false} />
        <PropModel url={cduModelUrl} {...EQUIPMENT_ANCHORS.cdu} tint="#2563eb" intensity={0.26} castShadow={false} />
        <Text position={[4.65, 2.18, -0.72]} fontSize={0.18} color="#c4b5fd" anchorX="center">PCS</Text>
        <Text position={[5.55, 1.82, -1.54]} fontSize={0.18} color="#7dd3fc" anchorX="center">液冷 CDU</Text>
      </group>
    </group>
  );
}

// ====================== Scene3D (contents of an R3F Canvas) ======================
function Scene3D() {
  const containers = useStore((s) => s.containers);
  const layers = useStore((s) => s.layers);
  const activeView = useStore((s) => s.activeView);
  const selectedDevice = useStore((s) => s.selectedDevice);
  const coolingMode = useStore((s) => s.coolingMode);
  const setSceneReady = useStore((s) => s.setSceneReady);

  const definition = viewDefinitionForIndex(activeView);
  const selectedClusterId = definition.sceneProfile === "asset" ? clusterIdForDevice(selectedDevice) : null;
  const selectedContainerIndex = containers.findIndex((container) => container.id === selectedClusterId);
  const selectedContainer = selectedContainerIndex >= 0 ? containers[selectedContainerIndex] : null;
  const selectedContainerPosition = selectedContainer
    ? containerSlotPosition(selectedContainerIndex)
    : null;
  const containerFocusActive = Boolean(selectedContainer);
  useEffect(() => {
    setSceneReady(true);
    return () => setSceneReady(false);
  }, [setSceneReady]);

  return (
    <>
      {/* background + atmosphere */}
      <color attach="background" args={["#111827"]} />
      <fog attach="fog" args={["#111827", 300, 760]} />

      {/* lighting */}
      <ambientLight intensity={1.15} color="#dbeafe" />
      <hemisphereLight args={["#ffffff", "#7c8a76", 1.35]} />
      <directionalLight
        position={[90, 140, 80]}
        intensity={2.2}
        color="#fff7e6"
      />
      <directionalLight position={[-120, 75, -80]} intensity={1.35} color="#bfe3ff" />
      <directionalLight position={[0, 110, -140]} intensity={1.1} color="#ffffff" />
      <pointLight position={[-15, 24, -10]} intensity={1.2} color="#7dd3fc" distance={120} />
      {selectedContainerPosition && (
        <pointLight
          position={[
            selectedContainerPosition[0] + 6,
            8,
            selectedContainerPosition[2] + 6,
          ]}
          intensity={5.5}
          color="#d9f7ff"
          distance={32}
          decay={1.4}
        />
      )}
      {/* controls + reset */}
      <SceneControls />

      {/* UHV 模型自带道路、光伏阵列、变电站及 BESS/ECC 站预留区。 */}
      <UhvSubstationScene
        visible={!containerFocusActive || !SCENE_RENDER_POLICY.hideUhvWhenFocused}
      />

      {/* ===== ECC station storage containers (4 x 8) ===== */}
      <group>
        <StorageContainerInstances containers={containers} />
        <CoolingSystem containers={containers} levelOverride={coolingMode} />
        <StorageContainerOverlays containers={containers} />
      </group>

      {selectedContainer && (
        <>
          <XRayContainer position={containerSlotPosition(selectedContainerIndex)} />
          <ContainerInterior container={selectedContainer} index={selectedContainerIndex} />
        </>
      )}
      {/* UHV 场景不包含风机，保留原有风机并移出 ECC 设备矩阵。 */}
      <group>
        {createWindTurbinePositions().map((position, index) => (
          <WindTurbine
            key={`${position[0]}-${position[2]}`}
            position={position}
            scale={WIND_LAYOUT.scale}
            speed={0.75 + (index % 4) * 0.12}
          />
        ))}
      </group>

      {/* yard labels */}
      {layers.labels && !containerFocusActive && (
        <>
          <Float speed={1.2} floatIntensity={0.4} rotationIntensity={0}>
            <Text
              position={[0, 8.5, -24]}
              fontSize={1.4}
              color="#00d4ff"
              anchorX="center"
              anchorY="middle"
              outlineWidth={0.02}
              outlineColor="#05080f"
            >
              ECC STATION · 32 ESS
            </Text>
          </Float>
          <Text position={[41, 30, 128]} fontSize={1.4} color="#7dd3fc" anchorX="center">
            WIND · 16 UNITS
          </Text>
        </>
      )}

      {/* click on empty space deselects nothing (keep selection); just prevent default */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -0.03, 0]}
        onPointerMissed={() => {}}
        visible={false}
      >
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial />
      </mesh>

    </>
  );
}

// ====================== Topology SLD (Single-Line Diagram) ======================
const TopologySLD = () => {
  return (
    <svg className="scene-svg" viewBox="0 0 1000 720" preserveAspectRatio="xMidYMid meet">
      <defs>
        <pattern id="sldgrid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M 40 0 L 0 0 0 40" stroke="#1f2738" strokeWidth="0.4" fill="none"/>
        </pattern>
        <linearGradient id="busbar" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#3b82f6"/>
          <stop offset="50%" stopColor="#00d4ff"/>
          <stop offset="100%" stopColor="#3b82f6"/>
        </linearGradient>
      </defs>
      <rect width="1000" height="720" fill="url(#sldgrid)" opacity="0.6"/>

      {/* Grid (top) — 220 kV cloud */}
      <g transform="translate(450 60)">
        <ellipse cx="50" cy="20" rx="60" ry="22" fill="rgba(59,130,246,0.15)" stroke="#3b82f6" strokeWidth="1.2"/>
        <text x="50" y="18" fontSize="14" fill="#3b82f6" textAnchor="middle" fontFamily="Orbitron" fontWeight="700">GRID</text>
        <text x="50" y="32" fontSize="9" fill="#9aa5bf" textAnchor="middle" fontFamily="JetBrains Mono">220 kV · 50 Hz</text>
      </g>

      {/* Grid -> Step-up transformer */}
      <line x1="500" y1="102" x2="500" y2="150" stroke="#3b82f6" strokeWidth="2"/>
      <text x="510" y="130" fontSize="10" fill="#3b82f6" fontFamily="JetBrains Mono">209 A · 80.4 MW</text>

      {/* Step-up transformer (visual: two interlocking circles) */}
      <g transform="translate(480 150)">
        <circle cx="10" cy="10" r="12" fill="none" stroke="#9aa5bf" strokeWidth="1.5"/>
        <circle cx="10" cy="22" r="12" fill="none" stroke="#9aa5bf" strokeWidth="1.5"/>
        <text x="40" y="14" fontSize="10" fill="#e6ebf5" fontFamily="JetBrains Mono">T1</text>
        <text x="40" y="26" fontSize="9" fill="#9aa5bf" fontFamily="JetBrains Mono">220/35 kV · 100 MVA</text>
      </g>

      {/* 35 kV busbar */}
      <line x1="120" y1="220" x2="880" y2="220" stroke="url(#busbar)" strokeWidth="4"/>
      <text x="120" y="212" fontSize="11" fill="#00d4ff" fontFamily="JetBrains Mono" fontWeight="600">BUSBAR · 35 kV</text>
      <text x="880" y="212" fontSize="9" fill="#9aa5bf" fontFamily="JetBrains Mono" textAnchor="end">f=50.02Hz · cosφ=0.98</text>

      {/* Branches */}
      {[
        {x: 180, color: "#facc15", title: "PV ARRAY", sub: "30 MW", arrow: "up"},
        {x: 380, color: "#60a5fa", title: "WIND FARM", sub: "24 MW", arrow: "up"},
        {x: 600, color: "#f97316", title: "ESS / PCS", sub: "20 MW / 50 MWh", arrow: "both"},
        {x: 820, color: "#10b981", title: "AUX LOAD", sub: "1.2 MW", arrow: "down"},
      ].map((b, i) => (
        <g key={i}>
          {/* breaker */}
          <line x1={b.x} y1="220" x2={b.x} y2="270" stroke={b.color} strokeWidth="1.5"/>
          <rect x={b.x-6} y="262" width="12" height="6" fill="rgba(10,14,26,1)" stroke={b.color} strokeWidth="1"/>
          <line x1={b.x-4} y1="285" x2={b.x+4} y2="276" stroke={b.color} strokeWidth="1.4"/>
          {/* drop */}
          <line x1={b.x} y1="285" x2={b.x} y2="350" stroke={b.color} strokeWidth="1.5"/>
          {/* device box */}
          <rect x={b.x-60} y="350" width="120" height="80" fill="rgba(10,14,26,0.8)" stroke={b.color} strokeWidth="1" rx="4"/>
          <text x={b.x} y="372" fontSize="11" fill={b.color} textAnchor="middle" fontFamily="Orbitron" fontWeight="600">{b.title}</text>
          <text x={b.x} y="388" fontSize="9" fill="#9aa5bf" textAnchor="middle" fontFamily="JetBrains Mono">{b.sub}</text>
          {/* flow arrow */}
          {b.arrow === "up" && (
            <g>
              <path d={`M ${b.x} 405 L ${b.x-3} 412 L ${b.x+3} 412 Z`} fill={b.color}>
                <animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite"/>
              </path>
              <text x={b.x} y="424" fontSize="9" fill={b.color} textAnchor="middle" fontFamily="JetBrains Mono">↑</text>
            </g>
          )}
          {b.arrow === "both" && (
            <g>
              <text x={b.x-12} y="424" fontSize="11" fill="#10b981" textAnchor="middle" fontFamily="JetBrains Mono">↑放</text>
              <text x={b.x+12} y="424" fontSize="11" fill="#f59e0b" textAnchor="middle" fontFamily="JetBrains Mono">↓充</text>
            </g>
          )}
          {b.arrow === "down" && (
            <text x={b.x} y="424" fontSize="9" fill={b.color} textAnchor="middle" fontFamily="JetBrains Mono">↓</text>
          )}
        </g>
      ))}

      {/* ESS sub-branches (clusters) */}
      <line x1="540" y1="450" x2="660" y2="450" stroke="#f97316" strokeWidth="1.2"/>
      {Array.from({length: 10}).map((_, i) => {
        const x = 540 + i * 13.3;
        const sev = i === 2 ? "critical" : i === 6 ? "warning" : "normal";
        const c = sev === "critical" ? "#ef4444" : sev === "warning" ? "#f59e0b" : "#10b981";
        return (
          <g key={i}>
            <line x1={x} y1="450" x2={x} y2="480" stroke={c} strokeWidth="0.8"/>
            <rect x={x-4} y="480" width="8" height="16" fill="rgba(10,14,26,0.9)" stroke={c} strokeWidth="0.6" rx="1"/>
            {sev === "critical" && <rect x={x-4} y="480" width="8" height="16" fill="none" stroke={c} strokeWidth="0.6" rx="1">
              <animate attributeName="opacity" values="1;0.3;1" dur="1s" repeatCount="indefinite"/>
            </rect>}
            <text x={x} y="510" fontSize="6" fill="#9aa5bf" textAnchor="middle" fontFamily="JetBrains Mono">A-{String(i+1).padStart(2,'0')}</text>
          </g>
        );
      })}
      <text x="600" y="540" fontSize="9" fill="#9aa5bf" textAnchor="middle" fontFamily="JetBrains Mono">10 × Battery Cluster (5 MWh each)</text>

      {/* Ground */}
      <g transform="translate(500 580)">
        <line x1="0" y1="0" x2="0" y2="20" stroke="#475569" strokeWidth="1"/>
        <line x1="-16" y1="20" x2="16" y2="20" stroke="#475569" strokeWidth="2"/>
        <line x1="-10" y1="26" x2="10" y2="26" stroke="#475569" strokeWidth="1.4"/>
        <line x1="-5" y1="32" x2="5" y2="32" stroke="#475569" strokeWidth="1"/>
        <text x="22" y="24" fontSize="8" fill="#5d6885" fontFamily="JetBrains Mono">PE</text>
      </g>

      {/* Side legend */}
      <g transform="translate(40 620)">
        <text x="0" y="0" fontSize="10" fill="#00d4ff" fontFamily="JetBrains Mono" fontWeight="600">▎电气拓扑图 · ELECTRICAL SLD</text>
        <text x="0" y="16" fontSize="9" fill="#5d6885" fontFamily="JetBrains Mono">实时数据采集 · 每 200ms 刷新</text>
        <text x="0" y="30" fontSize="9" fill="#10b981" fontFamily="JetBrains Mono">○ 正常运行  ○ 警告  ● 严重</text>
      </g>
    </svg>
  );
};

// ====================== Camera Grid ======================
const CameraGrid = ({ selectedCamera, onSelectCamera }) => {
  const cameras = [
    { id: "CAM-01", name: "CAM-01", location: "南门主入口", severity: "normal" },
    { id: "CAM-02", name: "CAM-02", location: "储能舱 A-01~A-05", severity: "normal" },
    { id: "CAM-03", name: "CAM-03", location: "储能舱 A-06~A-10", severity: "critical" },
    { id: "CAM-04", name: "CAM-04", location: "PCS 集装箱", severity: "normal" },
    { id: "CAM-05", name: "CAM-05", location: "风机 W-01/02 塔基", severity: "normal" },
    { id: "CAM-06", name: "CAM-06", location: "光伏阵列 PV-01", severity: "normal" },
    { id: "CAM-07", name: "CAM-07", location: "升压站 220kV", severity: "normal" },
    { id: "CAM-08", name: "CAM-08", location: "运维通道", severity: "normal" },
  ];
  const main = cameras.find(c => c.id === selectedCamera) || cameras[2];

  return (
    <div style={{position:"absolute", inset:0, padding:"54px 18px 18px", display:"grid", gridTemplateColumns:"1fr 280px", gap:14, minHeight:0}}>
      {/* main feed */}
      <div style={{position:"relative", display:"flex", flexDirection:"column", gap:10, minHeight:0}}>
        <div style={{position:"relative", flex:1, border:"1px solid var(--brand-primary)", borderRadius:"var(--r-lg)", overflow:"hidden", boxShadow:"var(--glow-primary)"}}>
          <CameraFeed {...main} selected scanLine/>
          {/* PTZ controls overlay */}
          <div style={{position:"absolute", bottom:18, right:18, display:"flex", flexDirection:"column", gap:6}}>
            <div style={{display:"flex", justifyContent:"center"}}>
              <button className="btn icon-only" style={{height:30, width:30}}><Icon name="chevUp" size={14}/></button>
            </div>
            <div style={{display:"flex", gap:6}}>
              <button className="btn icon-only" style={{height:30, width:30}}><Icon name="chevL" size={14}/></button>
              <button className="btn icon-only" style={{height:30, width:30}}><Icon name="target" size={12}/></button>
              <button className="btn icon-only" style={{height:30, width:30}}><Icon name="chevR" size={14}/></button>
            </div>
            <div style={{display:"flex", justifyContent:"center"}}>
              <button className="btn icon-only" style={{height:30, width:30}}><Icon name="chevD" size={14}/></button>
            </div>
          </div>
          {/* zoom controls */}
          <div style={{position:"absolute", bottom:18, left:18, display:"flex", flexDirection:"column", gap:6}}>
            <button className="btn icon-only" style={{height:30, width:30}}><Icon name="plus" size={14}/></button>
            <button className="btn icon-only" style={{height:30, width:30}}><Icon name="minus" size={14}/></button>
          </div>
          {/* AI overlay */}
          {main.severity === "critical" && (
            <div style={{position:"absolute", top:"38%", left:"24%", width:90, height:60, border:"1.5px solid #ef4444", boxShadow:"0 0 12px rgba(239,68,68,0.6)", animation:"alarm-box 1.2s infinite"}}>
              <div style={{position:"absolute", top:-22, left:0, fontSize:10, fontFamily:"var(--ff-mono)", color:"#ef4444", background:"rgba(10,14,26,0.9)", padding:"2px 6px", borderRadius:3}}>
                AI 识别 · 异常热源 96%
              </div>
            </div>
          )}
        </div>
      </div>
      {/* camera list */}
      <div style={{display:"flex", flexDirection:"column", gap:8, overflow:"auto", minHeight:0}}>
        <div style={{fontSize:11, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", letterSpacing:"0.1em", marginBottom:2}}>摄像头列表 · 8 在线</div>
        {cameras.map(c => (
          <CameraFeed key={c.id} {...c} selected={selectedCamera === c.id || (!selectedCamera && c.id === main.id)}
            onClick={() => onSelectCamera(c.id)}/>
        ))}
      </div>
    </div>
  );
};


export { Scene3D, TopologySLD, CameraGrid };
