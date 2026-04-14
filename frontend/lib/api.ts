import type { QueryResponse, SqlConnectionPayload, WorkspaceState } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function apiFetch(input: RequestInfo | URL, init?: RequestInit) {
  try {
    return await fetch(input, init);
  } catch {
    throw new Error(`Could not reach the backend API at ${API_BASE}. Check that the backend is running and NEXT_PUBLIC_API_BASE_URL points to it.`);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail || "Request failed");
  }
  return response.json() as Promise<T>;
}

export async function fetchWorkspace(): Promise<WorkspaceState> {
  return parseResponse<WorkspaceState>(await apiFetch(`${API_BASE}/api/workspace`, { cache: "no-store" }));
}

export async function uploadFiles(files: File[], shouldClean: boolean) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("should_clean", String(shouldClean));
  return parseResponse(await apiFetch(`${API_BASE}/api/uploads`, { method: "POST", body: form }));
}

export async function connectSqlSource(payload: SqlConnectionPayload) {
  return parseResponse(
    await apiFetch(`${API_BASE}/api/sources/sql`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function removeSource(sourceId: string) {
  return parseResponse(
    await apiFetch(`${API_BASE}/api/sources/${sourceId}`, {
      method: "DELETE",
    }),
  );
}

export async function askQuestion(question: string, allowJoins = false, preferredSourceId?: string): Promise<QueryResponse> {
  return parseResponse<QueryResponse>(
    await apiFetch(`${API_BASE}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, allow_joins: allowJoins, preferred_source_id: preferredSourceId }),
    }),
  );
}
