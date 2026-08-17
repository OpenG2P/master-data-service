import { useFetch } from "@/shared/hooks/useFetch";
import type { GeoLevel } from "../types";

export function useGeoLevels(enabled = true) {
  const { data, loading, error, execute } = useFetch<GeoLevel[]>({
    url: "/api/geo/geo-levels",
    enabled,
    options: {
      method: "POST",
      body: JSON.stringify({
        current_page: 1,
        page_size: 500,
        sort_by: "",
        filter_by: "",
        search_text: "",
      }),
    },
  });

  return {
    levels: Array.isArray(data) ? data : [],
    loading,
    error,
    refresh: execute,
  };
}
