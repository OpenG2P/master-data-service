import { withCsrfHeaders } from "@/shared/utils/csrf";
import type { GeoLevel, GeoLevelValue } from "@/types/geo";

type FetchGeoValuesOptions = {
  levelId: string;
  parentLevelValueId?: string;
  currentPage?: number;
  pageSize?: number;
  searchText?: string;
  sortBy?: string;
  signal?: AbortSignal;
};

async function postJson<T>(
  url: string,
  body: Record<string, unknown>,
  signal?: AbortSignal
): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: withCsrfHeaders("POST", {
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(body),
    signal,
  });

  const payload = await res.json().catch(() => null);

  if (res.status === 401) {
    throw new Error("UNAUTHORIZED");
  }

  if (!res.ok) {
    const message =
      (payload && typeof payload === "object" && "error" in payload
        ? String((payload as { error: unknown }).error)
        : null) || `Request failed (${res.status})`;
    throw new Error(message);
  }

  return payload as T;
}

export async function fetchGeoLevels(signal?: AbortSignal): Promise<GeoLevel[]> {
  const data = await postJson<GeoLevel[]>(
    "/api/geo-levels",
    {
      current_page: 1,
      page_size: 500,
      sort_by: "",
      filter_by: "",
      search_text: "",
    },
    signal
  );
  return Array.isArray(data) ? data : [];
}

export async function fetchGeoLevelValues(
  options: FetchGeoValuesOptions
): Promise<GeoLevelValue[]> {
  const data = await postJson<GeoLevelValue[]>(
    "/api/geo-level-values",
    {
      current_page: options.currentPage ?? 1,
      page_size: options.pageSize ?? 500,
      sort_by: options.sortBy ?? "",
      filter_by: "",
      search_text: options.searchText ?? "",
      level_id: options.levelId,
      parent_level_value_id: options.parentLevelValueId ?? "",
    },
    options.signal
  );
  return Array.isArray(data) ? data : [];
}
