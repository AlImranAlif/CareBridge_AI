const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
export const apiBaseUrl = (configuredApiBaseUrl || (process.env.NODE_ENV === "development" ? "http://localhost:8000/api/v1" : "")).replace(/\/$/, "");

export function apiUrl(path: string): string {
  if (!apiBaseUrl) throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured for this deployment.");
  return `${apiBaseUrl}${path}`;
}

export type ApiStatus = "online" | "offline";

export async function getApiStatus(): Promise<ApiStatus> {
  try {
    if (!apiBaseUrl) return "offline";
    const response = await fetch(apiUrl("/health/live"), {
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    return response.ok ? "online" : "offline";
  } catch {
    return "offline";
  }
}
