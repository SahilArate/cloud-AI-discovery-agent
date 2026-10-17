// Types mirror the response models in src/ai_discovery/api/main.py.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type CostSummary = {
  scan_id: string;
  llm_used: boolean;
  small_model: string;
  large_model: string;
  total_calls: number;
  calls_by_tier: Record<string, number>;
  escalated_calls: number;
  outcomes: Record<string, number>;
  total_cost_usd: number;
  all_large_cost_usd: number;
  saving_usd: number;
  cost_by_task: Record<string, number>;
  note: string;
};

export type InventoryItem = {
  asset_key: string;
  name: string;
  ai_verdict: string;
  activity_status: string;
  approval_status: string;
  risk_tier: string;
  owner: string | null;
  owner_source: string;
  region: string;
  hosting_type: string | null;
  review_required: boolean;
  decided_by: string;
  reasoning: string;
  first_seen: string;
  last_seen: string;
};

export type EvidenceItem = {
  evidence_id: string;
  evidence_type: string;
  strength: string;
  source: string;
  detail: string;
};

export type ObservationItem = {
  observation_id: string;
  scan_id: string;
  observed_at: string;
  ai_verdict: string;
  activity_status: string;
  approval_status: string;
  risk_tier: string;
  owner: string | null;
  owner_source: string;
  usage_count: number | null;
  usage_window_days: number | null;
  decided_by: string;
  review_required: boolean;
  reasoning: string;
  missing_evidence: string[];
  evidence: EvidenceItem[];
};

export type AssetDetail = {
  asset_key: string;
  name: string;
  provider: string;
  account_id: string;
  native_id: string;
  first_seen: string;
  last_seen: string;
  observations: ObservationItem[]; // newest first
};

export type ScopeItem = {
  region: string;
  service: string;
  status: string;
  resources_discovered: number;
  resources_inspected: number;
  errors: { code: string; operation: string; message?: string }[];
};

export type CoverageReport = {
  scan_id: string;
  scan_status: string;
  started_at: string;
  scopes_total: number;
  scopes_complete: number;
  scopes_with_gaps: number;
  scopes: ScopeItem[];
};

export type ChangeReport = {
  latest_scan_id: string;
  previous_scan_id: string | null;
  new_assets: string[];
  missing_assets: string[];
  note: string;
};

export type QueueItem = {
  asset_key: string;
  name: string;
  ai_verdict: string;
  approval_status: string;
  risk_tier: string;
  review_status: string;
  last_reviewer: string | null;
  last_reason: string | null;
  reasoning: string;
};

export type ReviewDecision = "approve" | "escalate";

export type ReviewRequest = {
  asset_key: string;
  decision: ReviewDecision;
  reviewer: string;
  reason: string;
};

export type ReviewItem = {
  review_id: string;
  asset_key: string;
  status: string;
  reviewer: string | null;
  reason: string | null;
  created_at: string;
};

export class ApiError extends Error {
  constructor(public status: number, path: string) {
    super(`${path} returned ${status}`);
  }
}

// A 404 means "nothing there yet" (no scans, unknown asset), so it returns null.
async function getJson<T>(path: string): Promise<T | null> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new ApiError(response.status, path);
  return (await response.json()) as T;
}

export const api = {
  inventory: async () => (await getJson<InventoryItem[]>("/inventory")) ?? [],
  // encodeURI keeps the slashes, because the backend route is /assets/{asset_key:path}.
  asset: (assetKey: string) => getJson<AssetDetail>(`/assets/${encodeURI(assetKey)}`),
  llmCost: () => getJson<CostSummary>("/llm/cost"),
  coverage: () => getJson<CoverageReport>("/coverage/latest"),
  changes: () => getJson<ChangeReport>("/changes"),
  reviewQueue: async () => (await getJson<QueueItem[]>("/reviews/queue")) ?? [],
  reviewHistory: async (assetKey: string) =>
    (await getJson<ReviewItem[]>(`/reviews/history?asset_key=${encodeURIComponent(assetKey)}`)) ??
    [],

  async submitReview(request: ReviewRequest): Promise<ReviewItem> {
    const response = await fetch(`${API_URL}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) throw new ApiError(response.status, "/reviews");
    return (await response.json()) as ReviewItem;
  },
};