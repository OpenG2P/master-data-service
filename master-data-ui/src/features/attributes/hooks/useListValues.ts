import { useCallback, useEffect, useState } from "react";
import { errorMessage, useCatalogueApi } from "@/features/catalogue/api";
import type { GetListValuesResponse, ListValue, VersionInfo, VersionRef } from "@/features/catalogue/types";

const PAGE_SIZE = 1000;
const MAX_PAGES = 50;

interface State {
    key: string;
    nonce: number;
    values?: ListValue[];
    version?: VersionInfo;
    error?: string;
}

/**
 * Every value of a list at a version (`/catalogue/get_list_values`, all pages), so the table can
 * drill down a hierarchy and search on the client like the previous attribute view did.
 */
export function useListValues(
    listCode: string | undefined,
    version: VersionRef,
    includeRetired: boolean,
    /** Change to force a reload (e.g. after a draft action elsewhere on the page). */
    reloadKey = 0,
) {
    const call = useCatalogueApi();
    const [nonce, setNonce] = useState(0);
    const [state, setState] = useState<State>({ key: "", nonce: -1 });
    const key = listCode ? JSON.stringify([listCode, version, includeRetired, reloadKey]) : "";

    useEffect(() => {
        if (!listCode) return;
        const controller = new AbortController();
        const load = async () => {
            const values: ListValue[] = [];
            let info: VersionInfo | undefined;
            for (let page = 1; page <= MAX_PAGES; page += 1) {
                const { payload } = await call<GetListValuesResponse>(
                    "get_list_values",
                    { list_code: listCode, version, include_retired: includeRetired },
                    { current_page: page, page_size: PAGE_SIZE },
                    controller.signal,
                );
                info = payload.version;
                values.push(...payload.values);
                if (values.length >= payload.total || payload.values.length < PAGE_SIZE) break;
            }
            return { values, version: info };
        };
        load().then(
            (r) => {
                if (!controller.signal.aborted) setState({ key, nonce, ...r });
            },
            (e: unknown) => {
                if (!controller.signal.aborted) setState({ key, nonce, error: errorMessage(e) });
            },
        );
        return () => controller.abort();
    }, [key, nonce, call, listCode, version, includeRetired]);

    const fresh = state.key === key;
    const loading = Boolean(listCode) && (!fresh || state.nonce !== nonce);
    const refresh = useCallback(() => setNonce((n) => n + 1), []);

    return {
        values: fresh ? state.values ?? [] : [],
        version: fresh ? state.version ?? null : null,
        error: fresh && !loading ? state.error : undefined,
        loading,
        refresh,
    };
}

export function valueHasChildren(valueCode: string, values: ListValue[]): boolean {
    return values.some((v) => v.parent_code === valueCode);
}
