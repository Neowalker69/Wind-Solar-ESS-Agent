"use client"

import { useQuery } from "@tanstack/react-query"

import { fetchStationApi, type AlarmItem, type DeviceTreeNode, type PowerFlowSummary, type TelemetrySeriesPoint } from "./station-api"

export const STATION_REALTIME_REFRESH_MS = 5_000

export function useDeviceTreeQuery(stationId: string) {
  return useQuery({ queryKey: ["device-tree", stationId], queryFn: () => fetchStationApi<DeviceTreeNode[]>("/devices/tree", { station_id: stationId, depth: 3 }) })
}

export function useAssetQuery(assetId: string | null) {
  return useQuery({ queryKey: ["asset", assetId], queryFn: () => fetchStationApi<DeviceTreeNode>(`/devices/${assetId}`), enabled: Boolean(assetId) })
}

export function useTelemetryHistoryQuery(assetId: string | null, range: { start: string; end: string }) {
  return useQuery({
    queryKey: ["telemetry-history", assetId, range],
    queryFn: () => fetchStationApi<{ series: TelemetrySeriesPoint[] }>("/telemetry/history", { device_id: assetId ?? undefined, metrics: "power_kw,temperature,soc", start: range.start, end: range.end, interval: "5m", aggregation: "avg" }),
    enabled: Boolean(assetId)
  })
}

export function alarmListQueryOptions() {
  return {
    queryKey: ["alarms"],
    queryFn: () => fetchStationApi<{ items: AlarmItem[] }>("/alarms", { status: "active", size: 100 }),
    refetchInterval: STATION_REALTIME_REFRESH_MS
  }
}

export function useAlarmListQuery() {
  return useQuery(alarmListQueryOptions())
}

export function usePowerFlowSummaryQuery(stationId: string) {
  return useQuery({ queryKey: ["power-flow", stationId], queryFn: () => fetchStationApi<{ summary: PowerFlowSummary }>("/power-flow/realtime", { station_id: stationId }), refetchInterval: 5_000 })
}
