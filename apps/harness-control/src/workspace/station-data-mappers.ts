import type { AlarmItem, DeviceTreeNode } from "./station-api"

export interface WorkspaceContainer {
  id: string
  stationDeviceId?: string
  severity: "normal" | "warning" | "critical"
  soc: number
  temp: number
  power: number
}

export interface WorkspaceAlarm {
  id: string
  deviceId: string | null
  stationDeviceId?: string
  severity: string
  title: string
  detail: string
  time: string
}

function finiteOrFallback(value: number | undefined, fallback: number): number {
  return Number.isFinite(value) ? value as number : fallback
}

function normalizedSeverity(value: string | undefined, fallback: WorkspaceContainer["severity"]): WorkspaceContainer["severity"] {
  return value === "normal" || value === "warning" || value === "critical" ? value : fallback
}

function flattenDeviceTree(nodes: DeviceTreeNode[]): DeviceTreeNode[] {
  return nodes.flatMap((node) => [node, ...flattenDeviceTree(node.children ?? [])])
}

/**
 * Go 的设备树只提供设备元数据与摘要；仅覆盖现有三维储能柜，避免把未知设备凭空变成场景实体。
 */
export function mapDeviceTreeToContainers(nodes: DeviceTreeNode[], fallback: WorkspaceContainer[]): WorkspaceContainer[] {
  const byReference = new Map<string, DeviceTreeNode>()
  for (const node of flattenDeviceTree(nodes)) {
    byReference.set(node.device_id, node)
    if (node.code) byReference.set(node.code, node)
  }

  return fallback.map((container) => {
    const node = byReference.get(container.stationDeviceId ?? container.id)
    if (!node) return container
    const latest = node.summary?.latest ?? {}
    return {
      id: container.id,
      ...(node.device_id !== container.id ? { stationDeviceId: node.device_id } : {}),
      severity: normalizedSeverity(node.summary?.status ?? node.status, container.severity),
      soc: finiteOrFallback(latest.soc, container.soc),
      temp: finiteOrFallback(latest.temperature ?? latest.temp, container.temp),
      power: finiteOrFallback(latest.power_kw ?? latest.power, container.power)
    }
  })
}

export function mapAlarmItems(items: AlarmItem[], nodes: DeviceTreeNode[] = []): WorkspaceAlarm[] {
  const byReference = new Map<string, DeviceTreeNode>()
  for (const node of flattenDeviceTree(nodes)) {
    byReference.set(node.device_id, node)
    if (node.code) byReference.set(node.code, node)
  }
  return items.map((item) => {
    const node = item.device_id ? byReference.get(item.device_id) : undefined
    const displayDeviceId = node?.code ?? item.device_id ?? null
    return {
      id: item.alarm_uuid,
      deviceId: displayDeviceId,
      ...(item.device_id && item.device_id !== displayDeviceId ? { stationDeviceId: item.device_id } : {}),
      severity: item.severity,
      title: item.message,
      detail: `${displayDeviceId ?? "未关联设备"} · ${item.status}`,
      time: Number.isNaN(Date.parse(item.triggered_at)) ? "--:--:--" : new Date(item.triggered_at).toISOString().slice(11, 19)
    }
  })
}
