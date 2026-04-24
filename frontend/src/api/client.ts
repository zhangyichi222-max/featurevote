const DEFAULT_API_BASE_URL =
  typeof window === "undefined"
    ? "http://localhost:8090/api/v1"
    : `${window.location.protocol}//${window.location.hostname}:8090/api/v1`;

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL;

type ApiValidationError = {
  loc?: Array<string | number>;
  msg?: string;
};

export class ApiError extends Error {
  fieldErrors: Record<string, string>;

  constructor(message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.fieldErrors = fieldErrors;
  }
}

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
    let fieldErrors: Record<string, string> = {};
    try {
      const parsed = JSON.parse(error) as { detail?: string | ApiValidationError[] };
      if (Array.isArray(parsed.detail)) {
        fieldErrors = Object.fromEntries(
          parsed.detail
            .map((item) => {
              const fieldName = item.loc
                ?.slice()
                .reverse()
                .find((part): part is string => typeof part === "string" && part !== "body");
              if (!fieldName || !item.msg) {
                return null;
              }
              return [fieldName, item.msg];
            })
            .filter((item): item is [string, string] => item !== null),
        );
        detail = Object.values(fieldErrors)[0] ?? "Request validation failed";
      } else {
        detail = parsed.detail ?? "";
      }
    } catch {
      // Fall through to the raw response body when the server did not send JSON.
    }
    throw new ApiError(detail || error || "Request failed", fieldErrors);
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
