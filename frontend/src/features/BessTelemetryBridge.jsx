import { useEffect } from "react";
import { useStore } from "../store";
import { resolveStationToken } from "./stationAuthClient";
import {
  BESS_TELEMETRY_INTERVAL_MS,
  applyBessTelemetrySnapshot,
  bessTelemetrySocketUrl,
  buildBessTelemetrySubscription,
  markBessRuntimeOverviewStale,
  summarizeBessRuntimeSnapshot,
} from "./stationTelemetryClient";

const RECONNECT_DELAY_MS = 3_000;

export function BessTelemetryBridge() {
  const refreshNonce = useStore((state) => state.runtimeRefreshNonce);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let socket = null;
    let reconnectTimer = null;

    const refreshStaleness = () => {
      const state = useStore.getState();
      state.replaceContainers(applyBessTelemetrySnapshot(state.containers, [], Date.now()));
      state.replaceRuntimeOverview(markBessRuntimeOverviewStale(state.runtimeOverview, Date.now()));
    };
    const staleTimer = window.setInterval(refreshStaleness, BESS_TELEMETRY_INTERVAL_MS);

    const connect = async () => {
      try {
        const token = await resolveStationToken();
        if (!active) return;
        socket = new WebSocket(bessTelemetrySocketUrl(token));
        socket.addEventListener("open", () => {
          const deviceIds = useStore.getState().containers.map(({ id }) => id);
          socket?.send(JSON.stringify(buildBessTelemetrySubscription(deviceIds)));
        });
        socket.addEventListener("message", (event) => {
          const message = JSON.parse(event.data);
          if (message.channel !== "telemetry" || !Array.isArray(message.data)) return;
          const state = useStore.getState();
          state.replaceContainers(
            applyBessTelemetrySnapshot(state.containers, message.data, Date.now()),
          );
          state.replaceRuntimeOverview(
            summarizeBessRuntimeSnapshot(message.data, state.runtimeOverview, message.timestamp),
          );
        });
        socket.addEventListener("close", () => {
          if (active) reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
        });
      } catch (error) {
        if (active && error?.name !== "AbortError") {
          const state = useStore.getState();
          state.replaceRuntimeOverview({
            ...state.runtimeOverview,
            status: state.runtimeOverview.updatedAt ? "stale" : "error",
            error: error?.message || "权威数据源连接失败",
          });
          reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
        }
      }
    };

    connect();
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(staleTimer);
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [refreshNonce]);

  return null;
}
