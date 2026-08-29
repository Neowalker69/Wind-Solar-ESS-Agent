export interface StationEnvelope<T> {
  code: number
  message: string
  data?: T
  trace_id: string
}

export interface DeviceTreeNode {
  device_id: string
  code?: string
  name: string
  station_id: string
  device_type: string
  status: string
  summary?: {
    status: string
    latest?: Record<string, number>
    active_alarm_count?: number
  }
  children: DeviceTreeNode[]
}

export interface AlarmItem {
  alarm_uuid: string
  device_id?: string
  severity: string
  message: string
  status: string
  triggered_at: string
}

export interface TelemetrySeriesPoint {
  time: string
  metric_key: string
  value: number
  count: number
}

export interface PowerFlowSummary {
  total_power_kw: number
  charging_power_kw: number
  discharging_power_kw: number
  node_count: number
  edge_count: number
}

const STATION_TOKEN_KEY = "station.accessToken"

function stationTokenStorage(): Storage | null {
  return typeof sessionStorage === "undefined" ? null : sessionStorage
}

function clearStationApiToken(): void {
  stationTokenStorage()?.removeItem(STATION_TOKEN_KEY)
}

export function resetStationApiTokenForTests(): void {
  clearStationApiToken()
}

export async function resolveStationApiToken(): Promise<string> {
  const cached = stationTokenStorage()?.getItem(STATION_TOKEN_KEY)
  if (cached) return cached
  throw new Error("station_login_required")
}

export function buildStationApiUrl(path: string, params: Record<string, string | number | undefined> = {}): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value))
  }
  const query = search.toString()
  return `/api/v1${path}${query ? `?${query}` : ""}`
}

export function unwrapStationEnvelope<T>(envelope: StationEnvelope<T>): T {
  if (envelope.code !== 0 || envelope.data === undefined) throw new Error(`station_api_${envelope.code}:${envelope.message}`)
  return envelope.data
}

export async function fetchStationApi<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = buildStationApiUrl(path, params)
  let token = await resolveStationApiToken()
  let response = await fetch(url, {
    credentials: "include",
    headers: { Authorization: `Bearer ${token}` },
  })
  if (response.status === 401) {
    clearStationApiToken()
    token = await resolveStationApiToken()
    response = await fetch(url, {
      credentials: "include",
      headers: { Authorization: `Bearer ${token}` },
    })
  }
  const envelope = await response.json() as StationEnvelope<T>
  if (!response.ok) throw new Error(`station_http_${response.status}:${envelope.message}`)
  return unwrapStationEnvelope(envelope)
}
