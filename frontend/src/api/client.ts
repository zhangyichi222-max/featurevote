const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8090/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const error = await response.text();
    let detail = "";
    try {
      const parsed = JSON.parse(error) as { detail?: string };
      detail = parsed.detail ?? "";
    } catch {
      // Fall through to the raw response body when the server did not send JSON.
    }
    throw new Error(detail || error || "Request failed");
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
