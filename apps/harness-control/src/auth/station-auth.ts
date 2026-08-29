export const STATION_TOKEN_KEY = "station.accessToken"

export interface StationTokenStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

interface AuthenticateStationOptions {
  fetchImpl?: typeof fetch
  storage?: StationTokenStorage | null
}

function browserSessionStorage(): StationTokenStorage | null {
  return typeof sessionStorage === "undefined" ? null : sessionStorage
}

export function readStationToken(storage: StationTokenStorage | null = browserSessionStorage()): string {
  return storage?.getItem(STATION_TOKEN_KEY) ?? ""
}

export function clearStationToken(storage: StationTokenStorage | null = browserSessionStorage()): void {
  storage?.removeItem(STATION_TOKEN_KEY)
}

export async function authenticateStation(
  username: string,
  password: string,
  options: AuthenticateStationOptions = {}
): Promise<string> {
  const fetchImpl = options.fetchImpl ?? fetch
  const storage = options.storage === undefined ? browserSessionStorage() : options.storage
  const response = await fetchImpl("/api/v1/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: username.trim(), password })
  })
  const envelope = await response.json().catch(() => null)
  const token = envelope?.data?.access_token

  if (!response.ok || envelope?.code !== 0 || typeof token !== "string" || !token) {
    if (response.status === 401) throw new Error("用户名或密码无效")
    throw new Error(envelope?.message || `登录服务返回 HTTP ${response.status}`)
  }

  storage?.setItem(STATION_TOKEN_KEY, token)
  return token
}

export async function validateStationToken(token: string, fetchImpl: typeof fetch = fetch): Promise<boolean> {
  if (!token) return false

  const response = await fetchImpl("/api/v1/users/me", {
    credentials: "include",
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!response.ok) return false

  const envelope = await response.json().catch(() => null)
  return envelope?.code === 0 && Boolean(envelope?.data?.id)
}
