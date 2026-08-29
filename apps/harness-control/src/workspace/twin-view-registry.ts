export type TwinViewId = "data" | "thermal" | "power-flow" | "alarms" | "video"

export interface TwinViewDefinition {
  id: TwinViewId
  routeSegment: TwinViewId
  label: string
  dashboard: "overview" | "thermal" | "power-flow" | "alarms" | "video"
  sceneProfile: "asset" | "thermal" | "power-flow" | "alarm" | "camera"
  legendProfile: "power" | "temperature" | "flow" | "alarm" | "camera"
  telemetryProfile: "asset" | "thermal" | "power-flow" | "alarms" | "video"
}

export const TWIN_VIEW_DEFINITIONS: readonly TwinViewDefinition[] = [
  { id: "data", routeSegment: "data", label: "数据视图", dashboard: "overview", sceneProfile: "asset", legendProfile: "power", telemetryProfile: "asset" },
  { id: "thermal", routeSegment: "thermal", label: "温度热力", dashboard: "thermal", sceneProfile: "thermal", legendProfile: "temperature", telemetryProfile: "thermal" },
  { id: "power-flow", routeSegment: "power-flow", label: "潮流分析", dashboard: "power-flow", sceneProfile: "power-flow", legendProfile: "flow", telemetryProfile: "power-flow" },
  { id: "alarms", routeSegment: "alarms", label: "告警分析", dashboard: "alarms", sceneProfile: "alarm", legendProfile: "alarm", telemetryProfile: "alarms" },
  { id: "video", routeSegment: "video", label: "视频监控", dashboard: "video", sceneProfile: "camera", legendProfile: "camera", telemetryProfile: "video" }
]

export const DEFAULT_TWIN_VIEW = TWIN_VIEW_DEFINITIONS[0]

export function resolveTwinView(candidate: string | undefined): TwinViewDefinition {
  return TWIN_VIEW_DEFINITIONS.find((definition) => definition.routeSegment === candidate) ?? DEFAULT_TWIN_VIEW
}

export function buildTwinViewHref(stationId: string, view: TwinViewId, assetId?: string | null): string {
  const params = assetId ? `?assetId=${encodeURIComponent(assetId)}` : ""
  return `/stations/${encodeURIComponent(stationId)}/${view}${params}`
}

export function viewIndexFor(view: TwinViewId): number {
  return TWIN_VIEW_DEFINITIONS.findIndex((definition) => definition.id === view)
}

/**
 * 旧工作台以数字索引保存视角；在迁移期间也必须反查同一份定义，不能再维护一套映射。
 */
export function viewDefinitionForIndex(index: number): TwinViewDefinition {
  return TWIN_VIEW_DEFINITIONS[index] ?? DEFAULT_TWIN_VIEW
}
