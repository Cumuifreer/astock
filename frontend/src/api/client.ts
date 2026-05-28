export type ApiRecord = Record<string, unknown>;

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string; message?: string };
      message = body.detail || body.message || message;
    } catch {
      // Keep the HTTP status text when the backend did not return JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function post<T>(path: string, payload: ApiRecord = {}): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(payload) });
}

export function patch<T>(path: string, payload: ApiRecord = {}): Promise<T> {
  return request<T>(path, { method: 'PATCH', body: JSON.stringify(payload) });
}
