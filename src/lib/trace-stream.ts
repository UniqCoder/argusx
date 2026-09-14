// ============================================================
// ARGUS — Streaming trace client
//
// Consumes the server-sent event stream from
// POST /api/v1/engine/trace/jobs -> GET .../jobs/{id}/events
// so the graph draws from the first hop instead of after the last one.
//
// WHY `fetch` AND NOT `EventSource`
// ---------------------------------
// `EventSource` cannot send request headers, so it cannot carry the
// `Authorization: Bearer` token this API requires. The two usual workarounds
// are both wrong here: putting a JWT in the query string leaks it into proxy
// logs and browser history, and opening the endpoint to cookie auth widens the
// auth surface for one convenience. `fetch` + a ReadableStream reader gives the
// same incremental delivery with normal headers.
// ============================================================
import { tokenStore, ApiRequestError } from "@/lib/api";
import type { EngineTraceResult, TaintNodeRead } from "@/lib/api-types";

const BASE =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ??
  "http://localhost:8000";

export interface TraceProgress {
  nodes_settled: number;
  frontier_size: number;
  hop: number;
  /** Tainted value still queued for expansion, in `asset`. */
  value_following: number;
  asset: string;
}

export interface TraceStreamHandlers {
  onStarted?: (info: { address: string; chain: string }) => void;
  /** One settled node. Its parent_address/tx_hash fields ARE its inbound edge. */
  onNode?: (node: TaintNodeRead) => void;
  onProgress?: (progress: TraceProgress) => void;
  onDone?: (result: EngineTraceResult) => void;
  onError?: (error: Error) => void;
}

interface StartJobResponse {
  job_id: string;
  status: string;
  events_url: string;
  snapshot_url: string;
}

async function startJob(body: unknown, signal: AbortSignal): Promise<StartJobResponse> {
  const res = await fetch(`${BASE}/api/v1/engine/trace/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(tokenStore.getAccess() ? { Authorization: `Bearer ${tokenStore.getAccess()}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let code = "TRACE_JOB_FAILED";
    let message = `Could not start the trace (HTTP ${res.status}).`;
    try {
      const payload = await res.json();
      code = payload?.error?.code ?? code;
      message = payload?.error?.message ?? message;
    } catch {
      /* non-JSON error body; the generic message stands */
    }
    throw new ApiRequestError(code, message, res.status);
  }
  return res.json();
}

/**
 * Parse an SSE byte stream into `{event, data}` records.
 *
 * Hand-rolled rather than pulled from a library because the format is four
 * lines of spec and the alternative is a dependency in the trace hot path.
 * Handles the one case that actually bites: a chunk boundary landing in the
 * middle of a record, which is common because node payloads carry full
 * proof paths and routinely exceed a single TCP segment.
 */
async function* parseSSE(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
): AsyncGenerator<{ event: string; data: string }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        let event = "message";
        const dataLines: string[] = [];
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length) yield { event, data: dataLines.join("\n") };
      }
    }
  } finally {
    reader.cancel().catch(() => {
      /* the stream is already going away */
    });
  }
}

/**
 * Run a trace and report each node as the engine settles it.
 *
 * Returns the completed result, so a caller that only wants the end state can
 * await it and ignore the handlers entirely.
 */
export async function streamTrace(
  request: { anchor_id: string; max_hops: number; max_nodes: number },
  handlers: TraceStreamHandlers,
  signal: AbortSignal,
): Promise<EngineTraceResult> {
  const job = await startJob(request, signal);

  const res = await fetch(`${BASE}${job.events_url}`, {
    headers: {
      Accept: "text/event-stream",
      ...(tokenStore.getAccess() ? { Authorization: `Bearer ${tokenStore.getAccess()}` } : {}),
    },
    signal,
  });
  if (!res.ok || !res.body) {
    throw new ApiRequestError(
      "TRACE_STREAM_FAILED",
      `Could not open the trace stream (HTTP ${res.status}).`,
      res.status,
    );
  }

  let result: EngineTraceResult | null = null;
  for await (const { event, data } of parseSSE(res.body, signal)) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      continue; // a malformed record is skipped, never allowed to kill the trace
    }
    switch (event) {
      case "started":
        handlers.onStarted?.(parsed as { address: string; chain: string });
        break;
      case "node":
        handlers.onNode?.(parsed as TaintNodeRead);
        break;
      case "progress":
        handlers.onProgress?.(parsed as TraceProgress);
        break;
      case "done":
        result = parsed as EngineTraceResult;
        handlers.onDone?.(result);
        break;
      case "error": {
        const e = parsed as { code: string; message: string };
        throw new ApiRequestError(e.code, e.message, 500);
      }
      case "heartbeat":
      default:
        break;
    }
  }

  if (!result) {
    // The stream ended without a `done` event: the connection dropped, or the
    // server restarted mid-trace. Say that, rather than rendering a partial
    // graph as if it were a finished trace.
    throw new ApiRequestError(
      "TRACE_STREAM_INCOMPLETE",
      "The trace stream ended before the trace finished.",
      0,
    );
  }
  return result;
}
