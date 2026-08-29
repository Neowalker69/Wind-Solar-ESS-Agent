"use client"

import dynamic from "next/dynamic"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useEffect } from "react"

import { useStore } from "../../../../frontend/src/store.js"

import { AgentStreamingWorkbench } from "../agent-workbench/AgentStreamingWorkbench"
import { ControlLoginGate } from "../auth/ControlLoginGate"
import { buildTwinViewHref, resolveTwinView, viewDefinitionForIndex, viewIndexFor } from "./twin-view-registry"
import { WorkspaceQueryProvider } from "./query-provider"
import { StationDataBridge } from "./station-data-bridge"

const ClientDigitalTwinApp = dynamic(
  () => import("../../../../frontend/src/components/App.jsx").then((module) => module.default),
  { ssr: false }
)

interface WorkspaceRouteState {
  activeView: number
  selectedDevice: string | null
}

function routeViewSegment(pathname: string, stationId: string): string | undefined {
  const prefix = `/stations/${stationId}/`
  return pathname.startsWith(prefix) ? pathname.slice(prefix.length).split("/")[0] : undefined
}

export function DigitalTwinWorkspace({ stationId }: { stationId: string }) {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const assetId = searchParams.get("assetId")
  const view = resolveTwinView(routeViewSegment(pathname, stationId))

  useEffect(() => {
    const state = useStore.getState()
    const viewIndex = viewIndexFor(view.id)
    if (state.activeView !== viewIndex) state.setActiveView(viewIndex)
    if (state.selectedDevice !== assetId) state.setSelectedDevice(assetId)
  }, [assetId, view.id])

  useEffect(() => useStore.subscribe((state: WorkspaceRouteState, previous: WorkspaceRouteState) => {
    if (state.activeView === previous.activeView && state.selectedDevice === previous.selectedDevice) return
    const nextView = viewDefinitionForIndex(state.activeView)
    const nextHref = buildTwinViewHref(stationId, nextView.id, state.selectedDevice)
    if (`${pathname}${searchParams.size ? `?${searchParams}` : ""}` !== nextHref) router.replace(nextHref, { scroll: false })
  }), [pathname, router, searchParams, stationId])

  return (
    <ControlLoginGate>
      <WorkspaceQueryProvider>
        <StationDataBridge stationId={stationId} />
        <ClientDigitalTwinApp
          AgentWorkbenchComponent={AgentStreamingWorkbench}
          agentStationId={stationId}
        />
      </WorkspaceQueryProvider>
    </ControlLoginGate>
  )
}
