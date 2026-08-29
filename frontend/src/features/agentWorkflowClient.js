import { parseSseFrames, unwrapEnvelope } from "./digitalTwinAdapters.js";

const SESSION_KEY = "digitalTwin.agentSessionId";
const STATION_TOKEN_KEY = "station.accessToken";
let runtimeBearerToken = "";

function storage() {
  return typeof sessionStorage === "undefined" ? null : sessionStorage;
}

async function readEnvelope(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok && !payload?.error) throw new Error(`Agent Gateway HTTP ${response.status}`);
  return unwrapEnvelope(payload);
}

export async function resolveAgentToken(signal, fetchImpl = fetch) {
  const stationToken = storage()?.getItem(STATION_TOKEN_KEY);
  if (stationToken) return stationToken;
  if (runtimeBearerToken) return runtimeBearerToken;
  const response = await fetchImpl("/api/v1/agent/bootstrap", { signal });
  const payload = await readEnvelope(response);
  runtimeBearerToken = payload.bearer_token || "";
  if (!runtimeBearerToken) throw new Error("Agent Gateway 需要登录凭据");
  return runtimeBearerToken;
}

export async function ensureAgentSession(siteId, token, signal, fetchImpl = fetch) {
  const current = storage()?.getItem(SESSION_KEY);
  if (current) return current;
  const response = await fetchImpl("/api/v1/agent/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ site_id: siteId }),
    signal,
  });
  const payload = await readEnvelope(response);
  storage()?.setItem(SESSION_KEY, payload.sessionId);
  return payload.sessionId;
}

export async function submitAgentMessage(sessionId, request, token, signal, fetchImpl = fetch) {
  const response = await fetchImpl(`/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(request),
    signal,
  });
  return readEnvelope(response);
}

function retryDelay(attempt) {
  return Math.min(5000, 250 * (2 ** attempt));
}

function sleep(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, milliseconds);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

export async function streamAgentRun(runId, token, signal, onEvents, fetchImpl = fetch, initialEventId = "0") {
  let lastEventId = initialEventId;
  let attempt = 0;
  while (!signal?.aborted) {
    try {
      const headers = { Accept: "text/event-stream", Authorization: `Bearer ${token}` };
      if (lastEventId !== "0") headers["Last-Event-ID"] = lastEventId;
      const response = await fetchImpl(`/api/v1/agent/runs/${encodeURIComponent(runId)}/stream`, { headers, signal });
      if (!response.ok) await readEnvelope(response);
      if (!response.body) throw new Error("浏览器不支持 Agent 流式响应");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const parsed = parseSseFrames(buffer);
        buffer = parsed.remainder;
        if (parsed.events.length) {
          lastEventId = String(parsed.events.at(-1).eventSequence || lastEventId);
          onEvents(parsed.events);
        }
        if (done) return lastEventId;
      }
    } catch (error) {
      if (error.name === "AbortError" || attempt >= 5) throw error;
      await sleep(retryDelay(attempt), signal);
      attempt += 1;
    }
  }
  throw new DOMException("Aborted", "AbortError");
}

export async function loadAgentRun(runId, token, signal, fetchImpl = fetch) {
  const response = await fetchImpl(`/api/v1/agent/runs/${encodeURIComponent(runId)}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  return readEnvelope(response);
}

export async function cancelAgentRun(runId, token, signal, fetchImpl = fetch) {
  const response = await fetchImpl(`/api/v1/agent/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  return readEnvelope(response);
}

export async function approveAgentAction(runId, container, token, signal, fetchImpl = fetch) {
  const response = await fetchImpl(`/api/v1/agent/runs/${encodeURIComponent(runId)}/approvals/create_work_order_draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      client_action_id: globalThis.crypto?.randomUUID?.() || `action_${Date.now()}`,
      device_id: container.stationDeviceId || container.id,
      decision: "approve",
      note: "运维工作台二次确认，仅创建待审核草稿",
    }),
    signal,
  });
  return readEnvelope(response);
}

export function resetAgentWorkflowClientForTest() {
  runtimeBearerToken = "";
}
