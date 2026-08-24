const KEY = "rag-eval-api-key";

export type Dataset = {
  id: string;
  name: string;
  filename: string | null;
  row_count: number;
  created_at: string;
};

export type Run = {
  id: string;
  dataset_id: string;
  adapter_type: string;
  adapter_config: Record<string, unknown>;
  evaluator: string;
  label: string | null;
  git_sha: string | null;
  status: string;
  error_message: string | null;
  is_baseline: boolean;
  means: Record<string, number> | null;
  error_count: number;
  created_at: string;
  completed_at: string | null;
};

export type RowScore = {
  question: string;
  answer: string | null;
  retrieved_contexts: string[];
  ground_truth: string | null;
  metrics: Record<string, number>;
  error: string | null;
};

export type RunDetail = Run & { rows: RowScore[] };

export type DiffResponse = {
  passed: boolean;
  threshold: number;
  baseline: Run;
  head: Run;
  deltas: Array<{
    metric: string;
    baseline: number;
    head: number;
    delta: number;
    dropped: boolean;
  }>;
  rows: Array<{
    index: number;
    question: string;
    baseline: RowScore | null;
    head: RowScore | null;
  }>;
};

export function getApiKey(): string {
  return sessionStorage.getItem(KEY) || "";
}

export function setApiKey(value: string): void {
  sessionStorage.setItem(KEY, value);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const key = getApiKey();
  if (key) headers.set("X-API-Key", key);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  auth: () => request<{ required: boolean }>("/api/auth"),
  datasets: () => request<Dataset[]>("/api/datasets"),
  dataset: (id: string) => request<Dataset>(`/api/datasets/${id}`),
  datasetRows: (id: string) =>
    request<Array<{ question: string; ground_truth: string | null; answer: string | null }>>(
      `/api/datasets/${id}/rows`,
    ),
  uploadDataset: async (file: File, name?: string) => {
    const body = new FormData();
    body.append("file", file);
    const query = name ? `?name=${encodeURIComponent(name)}` : "";
    return request<Dataset>(`/api/datasets${query}`, { method: "POST", body });
  },
  runs: (datasetId?: string) =>
    request<Run[]>(datasetId ? `/api/runs?dataset_id=${encodeURIComponent(datasetId)}` : "/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  createRun: (payload: {
    dataset_id: string;
    adapter: "traces" | "http";
    evaluator: "stub" | "ragas";
    sut_url?: string;
    sut_token?: string;
    timeout_seconds?: number;
    label?: string;
    git_sha?: string;
  }) =>
    request<Run>("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  baseline: (id: string) => request<Run>(`/api/runs/${id}/baseline`, { method: "POST" }),
  diff: (headId: string, against: string, threshold = 0.05) =>
    request<DiffResponse>(
      `/api/runs/${headId}/diff?against=${encodeURIComponent(against)}&threshold=${threshold}`,
    ),
};

export function fmt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(3);
}
