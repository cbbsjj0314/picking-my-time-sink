const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "/api" : "");

type ErrorPayload = {
  detail?: string;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function requestJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;

    try {
      const payload = (await response.json()) as ErrorPayload;
      if (typeof payload.detail === "string" && payload.detail.length > 0) {
        detail = payload.detail;
      }
    } catch {
      // Ignore invalid error bodies and keep the fallback message.
    }

    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}
