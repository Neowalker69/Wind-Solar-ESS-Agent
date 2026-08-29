"use client"

import { useEffect } from "react"

import { useStore } from "../../../../frontend/src/store.js"

import { mapAlarmItems, mapDeviceTreeToContainers } from "./station-data-mappers"
import { useAlarmListQuery, useDeviceTreeQuery } from "./station-queries"

/** 把 TanStack Query 的服务端状态投影到既有数字孪生 UI 状态，不改写 Go API 或三维实体模型。 */
export function StationDataBridge({ stationId }: { stationId: string }) {
  const deviceTree = useDeviceTreeQuery(stationId)
  const alarms = useAlarmListQuery()

  useEffect(() => {
    if (!deviceTree.data?.length) return
    const state = useStore.getState()
    state.replaceContainers(mapDeviceTreeToContainers(deviceTree.data, state.containers))
  }, [deviceTree.data])

  useEffect(() => {
    if (!alarms.data?.items) return
    useStore.getState().replaceAlerts(mapAlarmItems(alarms.data.items, deviceTree.data ?? []))
  }, [alarms.data, deviceTree.data])

  return null
}
