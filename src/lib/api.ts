// ============================================================
// ARGUS — Central API Client
// Base URL: VITE_API_BASE_URL (default http://localhost:8000)
// Auth: JWT Bearer, auto-refreshes on 401
// ============================================================
import type {
  LoginRequest,
  LoginResponse,
  RefreshResponse,
  RiskResponse,
  DepositCheckRequest,
  DepositCheckResponse,
  AnchorCreate,
  AnchorRead,
  EngineTraceRequest,
  EngineTraceResult,
  CorrelateRequest,
  CorrelateResponse,
  Paginated,
  Case,
  CaseCreate,
  CasePatch,
  Alert,
  Complaint,
  ComplaintDetail,
  HealthResponse,
  Chain,
  CaseStatus,
} from "./api-types";

const BASE =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ??
  "http://localhost:8000";

// ── Token storage (sessionStorage — cleared when tab closes) ──────────────
const KEYS = {
  access: "ug_access",
  refresh: "ug_refresh",
  role: "ug_role",
} as const;

export const tokenStore = {
  getAccess: () => sessionStorage.getItem(KEYS.access),
  getRefresh: () => sessionStorage.getItem(KEYS.refresh),
  getRole: () => sessionStorage.getItem(KEYS.role),
  set: (access: string, refresh: string, role: string) => {
    sessionStorage.setItem(KEYS.access, access);
    sessionStorage.setItem(KEYS.refresh, refresh);
    sessionStorage.setItem(KEYS.role, role);
  },
  clear: () => {
    sessionStorage.removeItem(KEYS.access);
    sessionStorage.removeItem(KEYS.refresh);
    sessionStorage.removeItem(KEYS.role);
  },
};

// ── Typed error class ──────────────────────────────────────────────────────
export class ApiRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

// ── Core request helper ────────────────────────────────────────────────────
let _refreshing = false;

async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const token = tokenStore.getAccess();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string> | undefined) ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  // Auto-refresh once on 401
  if (res.status === 401 && retry && !_refreshing) {
    const refreshToken = tokenStore.getRefresh();
    if (refreshToken) {
      _refreshing = true;
      try {
        const rRes = await fetch(`${BASE}/api/v1/auth/refresh`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (rRes.ok) {
          const { access_token } = (await rRes.json()) as RefreshResponse;
          tokenStore.set(
            access_token,
            refreshToken,
            tokenStore.getRole() ?? "investigator",
          );
          _refreshing = false;
          return request<T>(path, options, false);
        }
      } catch {
        // refresh failed — fall through
      }
      _refreshing = false;
      tokenStore.clear();
    }
  }

  if (!res.ok) {
    let code = `HTTP_${res.status}`;
    let message = res.statusText || `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as {
        error?: { code?: string; message?: string };
      };
      if (body.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      }
    } catch {
      /* non-JSON body — keep defaults */
    }
    throw new ApiRequestError(code, message, res.status);
  }

  // Binary responses (PDF report)
  if ((res.headers.get("content-type") ?? "").includes("application/pdf")) {
    return (await res.blob()) as unknown as T;
  }

  return res.json() as Promise<T>;
}

// ── Auth ───────────────────────────────────────────────────────────────────
export async function login(body: LoginRequest): Promise<LoginResponse> {
  const data = await request<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
  tokenStore.set(data.access_token, data.refresh_token, data.role);
  return data;
}

export function logout(): void {
  tokenStore.clear();
}

// ── Health ─────────────────────────────────────────────────────────────────
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

// ── Wallets ────────────────────────────────────────────────────────────────
// Note: the v1 GET /wallets/{address}/trace endpoint is intentionally not
// wrapped here anymore — it only lists an address's own direct transactions
// (no real multi-hop, no real mixer/bridge/VASP classification) and the
// frontend now routes wallet tracing through the real v2 provenance engine
// (createAnchor + runEngineTrace below). The v1 route itself still exists
// server-side for report_service.py's internal use and its own tests.
export function getWalletRisk(
  address: string,
  chain: Chain,
): Promise<RiskResponse> {
  return request<RiskResponse>(
    `/api/v1/wallets/${encodeURIComponent(address)}/risk?chain=${chain}`,
  );
}

// ── Provenance engine (v2) ─────────────────────────────────────────────────
export function createAnchor(body: AnchorCreate): Promise<AnchorRead> {
  return request<AnchorRead>("/api/v1/anchors", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function runEngineTrace(
  body: EngineTraceRequest,
): Promise<EngineTraceResult> {
  return request<EngineTraceResult>("/api/v1/engine/trace", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function checkDeposit(
  body: DepositCheckRequest,
): Promise<DepositCheckResponse> {
  return request<DepositCheckResponse>("/api/v1/wallets/deposit-check", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Correlation ────────────────────────────────────────────────────────────
export function correlate(body: CorrelateRequest): Promise<CorrelateResponse> {
  return request<CorrelateResponse>("/api/v1/correlate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Cases ──────────────────────────────────────────────────────────────────
export function listCases(params?: {
  status?: CaseStatus;
  page?: number;
  page_size?: number;
}): Promise<Paginated<Case>> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.page) q.set("page", String(params.page));
  if (params?.page_size) q.set("page_size", String(params.page_size));
  const qs = q.toString();
  return request<Paginated<Case>>(`/api/v1/cases${qs ? `?${qs}` : ""}`);
}

export function getCase(id: string): Promise<Case> {
  return request<Case>(`/api/v1/cases/${id}`);
}

export function createCase(body: CaseCreate): Promise<Case> {
  return request<Case>("/api/v1/cases", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchCase(id: string, body: CasePatch): Promise<Case> {
  return request<Case>(`/api/v1/cases/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function getCaseReport(id: string): Promise<Blob> {
  return request<Blob>(`/api/v1/cases/${id}/report`);
}

// ── Alerts ─────────────────────────────────────────────────────────────────
export function listAlerts(params?: {
  resolved?: boolean;
  page?: number;
  page_size?: number;
}): Promise<Paginated<Alert>> {
  const q = new URLSearchParams();
  if (params?.resolved !== undefined)
    q.set("resolved", String(params.resolved));
  if (params?.page) q.set("page", String(params.page));
  if (params?.page_size) q.set("page_size", String(params.page_size));
  const qs = q.toString();
  return request<Paginated<Alert>>(`/api/v1/alerts${qs ? `?${qs}` : ""}`);
}

// ── Complaints ─────────────────────────────────────────────────────────────
export function listComplaints(params?: {
  state?: string;
  fraud_typology?: string;
  page?: number;
}): Promise<Paginated<Complaint>> {
  const q = new URLSearchParams();
  if (params?.state) q.set("state", params.state);
  if (params?.fraud_typology) q.set("fraud_typology", params.fraud_typology);
  if (params?.page) q.set("page", String(params.page));
  const qs = q.toString();
  return request<Paginated<Complaint>>(
    `/api/v1/complaints${qs ? `?${qs}` : ""}`,
  );
}

export function getComplaint(id: string): Promise<ComplaintDetail> {
  return request<ComplaintDetail>(`/api/v1/complaints/${id}`);
}
