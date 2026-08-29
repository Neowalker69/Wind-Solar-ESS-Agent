export const P2_AUTHORITATIVE_STATION_ID = "ess-station-01"

export const DEFAULT_STATION_VIEW = "data"

export function defaultStationHref(): string {
  return `/stations/${P2_AUTHORITATIVE_STATION_ID}/${DEFAULT_STATION_VIEW}`
}
