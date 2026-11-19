const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type ApiStatus = "online" | "offline";

export async function getApiStatus(): Promise<ApiStatus> {
  try {
    const response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/health/live`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    return response.ok ? "online" : "offline";
  } catch {
    return "offline";
  }
}
