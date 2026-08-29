const STATION_TOKEN_KEY = "station.accessToken";
let runtimeBootstrapToken = "";
let bootstrapPromise = null;

export async function resolveStationToken() {
  const token = sessionStorage.getItem(STATION_TOKEN_KEY);
  if (token) return token;
  if (runtimeBootstrapToken) return runtimeBootstrapToken;

  if (!bootstrapPromise) {
    bootstrapPromise = fetch("/api/v1/agent/bootstrap")
      .then(async (response) => {
        const payload = await response.json().catch(() => null);
        const bearerToken = payload?.data?.bearer_token || "";
        if (!response.ok || !bearerToken) {
          throw new Error(payload?.message || "station_login_required");
        }
        runtimeBootstrapToken = bearerToken;
        sessionStorage.setItem(STATION_TOKEN_KEY, bearerToken);
        return bearerToken;
      })
      .finally(() => {
        bootstrapPromise = null;
      });
  }

  return bootstrapPromise;
}

export function resetStationTokenForTests() {
  runtimeBootstrapToken = "";
  bootstrapPromise = null;
  sessionStorage?.removeItem(STATION_TOKEN_KEY);
}
