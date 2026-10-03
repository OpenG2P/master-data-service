import { useMemo } from "react";
import { useCatalogueQuery } from "@/features/catalogue/api";
import type { GetListsResponse } from "@/features/catalogue/types";

const PAYLOAD = { include_unpublished: true };

/** All code lists (`/catalogue/get_lists`): owner, current published version, open draft. */
export function useCatalogueLists(searchText?: string) {
    const { data, loading, error, reload } = useCatalogueQuery<GetListsResponse>("get_lists", PAYLOAD);
    const all = useMemo(() => data?.lists ?? [], [data]);

    const filtered = useMemo(() => {
        const q = searchText?.trim().toLowerCase();
        if (!q) return all;
        return all.filter(
            (l) =>
                l.list_code?.toLowerCase().includes(q) ||
                l.display?.toLowerCase().includes(q) ||
                l.owner_org?.toLowerCase().includes(q) ||
                l.list_id.toLowerCase().includes(q),
        );
    }, [all, searchText]);

    return { lists: filtered, allLists: all, loading: loading && !data, error, refresh: reload };
}
