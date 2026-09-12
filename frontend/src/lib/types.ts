export type Asset = {
  id: string;
  name: string;
  kind: "image" | "video" | "audio" | "text";
  sha256: string;
  size: number;
  created_at: string;
  details: {
    duration?: number;
    width?: number;
    height?: number;
    has_audio?: boolean;
    preview?: string;
    preview_text?: string;
    composition?: Record<string, unknown>;
    characters?: number;
  };
};
export type Project = {
  id: string;
  name: string;
  brief: string;
  asset_id: string | null;
  reference_ids: string[];
  constraints: Record<string, unknown>;
  created_at: string;
};
export type Metric = {
  metric: string;
  value: number;
  per_reference: { reference_id: string; value: number }[];
  range: number[];
  interpretation: string;
};
export type Evaluation = {
  id: string;
  asset_id: string;
  evaluator: string;
  profile: string;
  created_at: string;
  duration_seconds: number;
  evidence: {
    shape: number[];
    times: number[];
    left_mean: number[];
    right_mean: number[];
    rms: number[];
    range: number[];
    mesh: string;
    seconds: number;
    peak_cuda_bytes: number;
    modalities: string[];
    input_adaptation?: string;
    limitations: string[];
    transcript_source?: string;
    tsam?: {
      status: string;
      reason?: string;
      labels?: string[];
      windows?: {
        start: number;
        end: number;
        logits: number[];
        top_class: string;
      }[];
      seconds?: number;
      interpretation?: string;
    };
    kragel?: {
      status: string;
      reason?: string;
      labels?: string[];
      times?: number[];
      trajectories?: Record<string, number[]>;
      aggregate?: Record<string, number>;
      top_pattern?: string;
      interpretation?: string;
      limitations?: string[];
    };
    response_ensemble?: ResponseEnsemble;
    emotion_decoder?: { status: string; reason: string };
  };
};
export type ResponseEnsemble = {
  profile: string;
  values: Record<string, number | null>;
  sources: {
    tsam?: Record<string, number> | null;
    kragel?: Record<string, number> | null;
  };
  source_weights: Record<string, number>;
  active_sources: string[];
  disagreement: Record<string, number>;
  mean_disagreement: number | null;
  confidence: string;
  interpretation: string;
};

export type Experiment = {
  id: string;
  sequence: number;
  operator: string;
  hypothesis: string;
  asset_id: string | null;
  baseline_score: number | null;
  candidate_score: number | null;
  decision: string;
  evidence: { gain?: number; reason?: string; reference_tradeoff?: boolean };
  created_at: string;
};
export type RunEvent = {
  id: number;
  kind: string;
  message: string;
  details: Record<string, unknown>;
  created_at: string;
};
export type Run = {
  id: string;
  project_id: string;
  mode: string;
  status: string;
  stage: string;
  error: string | null;
  stop_reason: string | null;
  max_evaluations: number;
  evaluations_used: number;
  compute_seconds: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: {
    baseline_asset_id?: string;
    best_asset_id?: string;
    baseline_evaluation_id?: string;
    best_evaluation_id?: string;
    baseline_metric?: Metric;
    best_metric?: Metric;
    scope?: string;
    policy?: string;
    planner?: string;
    metric?: string;
    baseline_response?: ResponseEnsemble;
    best_response?: ResponseEnsemble;
  };
  experiments?: Experiment[];
  events?: RunEvent[];
};
export type Capability = {
  execution?: { paused: boolean; reason: string | null };
  models: { name: string; status: string }[];
  tribe: {
    status: string;
    meaning: string;
    last_technical_test?: {
      evaluation_id: string;
      profile: string;
      created_at: string;
    } | null;
  };
  tsam: { status: string; reason: string };
  kragel: { status: string; reason?: string; meaning?: string; profile?: string; missing?: string[] };
  generation_providers?: { name: string; status: string; detail: string; capabilities: string[] }[];
  asr: { status: string; purpose: string };
  integrations: { name: string; status: string; purpose: string }[];
  modalities: Record<string, string>;
  claim_boundaries: string[];
};
export type Dashboard = {
  assets: Asset[];
  projects: Project[];
  runs: Run[];
  evaluations: Evaluation[];
  counts: {
    assets: number;
    projects: number;
    evaluations: number;
    experiments: number;
  };
  capabilities: Capability;
};
export type PolicyStat = {
  context: string;
  operator: string;
  attempts: number;
  successes: number;
  failures: number;
  mean_gain: number;
  mean_seconds: number;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api/" + path, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
      response.status,
    );
  }
  return response.json() as Promise<T>;
}
export const score = (value?: number | null) =>
  typeof value === "number" ? value.toFixed(3) : "—";
export const size = (bytes: number) =>
  bytes > 1024 * 1024
    ? (bytes / 1024 / 1024).toFixed(1) + " MB"
    : Math.round(bytes / 1024) + " KB";
export const seconds = (value: number) =>
  value >= 60
    ? Math.floor(value / 60) + "m " + Math.round(value % 60) + "s"
    : value.toFixed(1) + "s";
