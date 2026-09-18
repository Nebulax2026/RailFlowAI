export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    throw new ApiError(Array.isArray(detail) ? detail.join(" ") : detail || `Request failed (${response.status}).`, response.status);
  }
  return payload as T;
}

