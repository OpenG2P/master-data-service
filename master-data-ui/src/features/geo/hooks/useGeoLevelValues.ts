import { useFetch } from "@/shared/hooks/useFetch";
import type { GeoLevelValue } from "../types";

export function useGeoLevelValues(
  levelId?: string,
  parentLevelValueId?: string,
  page?: number,
  pageSize?: number,
  searchText?: string,
) {
  const { data, loading, error, execute } = useFetch<GeoLevelValue[]>({
    url: "/api/geo/geo-level-values",
    enabled: !!levelId,
    options: {
      method: "POST",
      body: JSON.stringify({
        current_page: page ?? 1,
        page_size: pageSize ?? 500,
        sort_by: "",
        filter_by: "",
        search_text: searchText?.trim() ?? "",
        level_id: levelId,
        parent_level_value_id: parentLevelValueId ?? "",
      }),
    },
  });

  return {
    values: Array.isArray(data) ? data : [],
    loading,
    error,
    refresh: execute,
  };
}
