import type { ReactNode } from "react"

import { DigitalTwinWorkspace } from "../../../src/workspace/digital-twin-workspace"

export default async function StationLayout({ children, params }: { children: ReactNode; params: Promise<{ stationId: string }> }) {
  const { stationId } = await params
  return <><DigitalTwinWorkspace stationId={stationId} />{children}</>
}
