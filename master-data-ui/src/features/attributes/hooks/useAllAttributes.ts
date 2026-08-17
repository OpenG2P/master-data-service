import { useFetch } from "@/shared/hooks/useFetch";
import type { Attribute } from "../types";

export function useAllAttributes(searchText?: string) {
    const { data, loading, error, execute } = useFetch<{
        attributes: Attribute[];
    }>({
        url: "/api/attributes/get-attributes",
        options: {
            method: "POST",
            body: JSON.stringify({
                current_page: 1,
                page_size: 1000,
                include_domains: true,
            }),
        },
    });

    const all = data?.attributes ?? [];

    const filtered = searchText?.trim()
        ? all.filter((a) => {
              const q = searchText.trim().toLowerCase();
              return (
                  a.attribute_code?.toLowerCase().includes(q) ||
                  a.attribute_display?.toLowerCase().includes(q)
              );
          })
        : all;

    return {
        attributes: filtered,
        allAttributes: all,
        loading,
        error,
        refresh: execute,
    };
}
