"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/Authcontext";
import { withCsrfHeaders } from "@/shared/utils/csrf";
import type { CataloguePagination } from "./types";

/** Error of a catalogue call: the backend's message and code (e.g. G2P-CAT-403). */
export class CatalogueApiError extends Error {
    code?: string;
    status: number;

    constructor(message: string, status: number, code?: string) {
        super(message);
        this.name = "CatalogueApiError";
        this.status = status;
        this.code = code;
    }
}

export interface CatalogueResult<T> {
    payload: T;
    pagination: CataloguePagination | null;
}

export interface PaginationInput {
    current_page?: number;
    page_size?: number;
}

/** Message to show for any error thrown by a catalogue call. */
export function errorMessage(error: unknown, fallback = "Something went wrong"): string {
    if (error instanceof CatalogueApiError) {
        return error.code && !error.message.includes(error.code)
            ? `${error.message} (${error.code})`
            : error.message;
    }
    if (error instanceof Error) return error.message;
    return fallback;
}

/**
 * Returns `call(op, payload, pagination?)`, which POSTs to `/api/catalogue/<op>` and resolves
 * to `{payload, pagination}` or throws a CatalogueApiError carrying the backend's message.
 */
export function useCatalogueApi() {
    const { handleUnauthorized } = useAuth();

    return useCallback(
        async <T,>(
            op: string,
            payload: object = {},
            pagination?: PaginationInput,
            signal?: AbortSignal,
        ): Promise<CatalogueResult<T>> => {
            const res = await fetch(`/api/catalogue/${op}`, {
                method: "POST",
                credentials: "include",
                headers: withCsrfHeaders("POST", { "Content-Type": "application/json" }),
                body: JSON.stringify({ payload, pagination }),
                signal,
            });
            if (res.status === 401) {
                handleUnauthorized();
                throw new CatalogueApiError("Unauthorized", 401, "G2P-AUT-401");
            }
            let body: unknown = null;
            try {
                body = await res.json();
            } catch {
                body = null;
            }
            const obj = (body ?? {}) as Record<string, unknown>;
            if (!res.ok) {
                const nested = Array.isArray(obj.errors) ? (obj.errors[0] as Record<string, unknown>) : undefined;
                const message = String(
                    obj.statusText || nested?.message || res.statusText || `Error ${res.status}`,
                );
                const code = obj.code ?? nested?.code;
                throw new CatalogueApiError(message, res.status, code != null ? String(code) : undefined);
            }
            if (!("payload" in obj)) {
                throw new CatalogueApiError(String(obj.statusText || "Empty response"), res.status);
            }
            return {
                payload: obj.payload as T,
                pagination: (obj.pagination as CataloguePagination | null) ?? null,
            };
        },
        [handleUnauthorized],
    );
}

interface QueryState<T> {
    key: string | null;
    nonce: number;
    data?: T;
    pagination?: CataloguePagination | null;
    error?: string;
    errorCode?: string;
}

/**
 * Loads `op` with `payload` (skipped while payload is null) and reloads when either changes.
 * Keeps the previous data visible while a reload of the same request is running.
 */
export function useCatalogueQuery<T>(
    op: string,
    payload: object | null,
    pagination?: PaginationInput,
) {
    const call = useCatalogueApi();
    const key = payload === null ? null : JSON.stringify([op, payload, pagination ?? null]);
    const [nonce, setNonce] = useState(0);
    const [state, setState] = useState<QueryState<T>>({ key: null, nonce: -1 });

    useEffect(() => {
        if (key === null) return;
        const controller = new AbortController();
        const [o, p, pg] = JSON.parse(key) as [string, object, PaginationInput | null];
        call<T>(o, p, pg ?? undefined, controller.signal).then(
            (result) => {
                if (controller.signal.aborted) return;
                setState({ key, nonce, data: result.payload, pagination: result.pagination });
            },
            (error: unknown) => {
                if (controller.signal.aborted) return;
                if (error instanceof DOMException && error.name === "AbortError") return;
                setState({
                    key,
                    nonce,
                    error: errorMessage(error),
                    errorCode: error instanceof CatalogueApiError ? error.code : undefined,
                });
            },
        );
        return () => controller.abort();
    }, [key, nonce, call]);

    const sameKey = key !== null && state.key === key;
    const loading = key !== null && (!sameKey || state.nonce !== nonce);
    const reload = useCallback(() => setNonce((n) => n + 1), []);

    return {
        data: sameKey ? state.data : undefined,
        pagination: sameKey ? state.pagination ?? null : null,
        error: sameKey && !loading ? state.error : undefined,
        errorCode: sameKey && !loading ? state.errorCode : undefined,
        loading,
        reload,
    };
}
