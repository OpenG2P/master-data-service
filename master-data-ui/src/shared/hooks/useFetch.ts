import { useAuth } from "@/context/Authcontext";
import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { withCsrfHeaders } from "@/shared/utils/csrf";

interface UseFetchConfig {
    url?: string | null;
    options?: RequestInit;
    enabled?: boolean;
}

export function useFetch<T = any>({
    url = null,
    options,
    enabled = true,
}: UseFetchConfig = {}) {
    const [data, setData] = useState<T | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState<boolean>(true);

    const { handleUnauthorized } = useAuth()

    const controllerRef = useRef<AbortController | null>(null);

    // Memoize options to prevent infinite loops
    const optionsString = useMemo(() => JSON.stringify(options), [options]);

    const reset = useCallback(() => {
        if (controllerRef.current) {
            controllerRef.current.abort();
            controllerRef.current = null;
        }
        setData(null);
        setError(null);
        setLoading(false);
    }, []);

    // Manual execute method for on-demand API calls
    const execute = useCallback(async (
        executeUrl?: string,
        executeOptions?: RequestInit
    ): Promise<T | null> => {
        const finalUrl = executeUrl || url;
        const finalOptions = executeOptions || options;

        if (!finalUrl) {
            throw new Error('URL is required for execute');
        }

        if (controllerRef.current) {
            controllerRef.current.abort();
        }

        const controller = new AbortController();
        controllerRef.current = controller;

        setLoading(true);
        setError(null);

        try {
            const method = (finalOptions?.method || 'GET').toUpperCase();
            const res = await fetch(finalUrl, {
                ...finalOptions,
                credentials: 'include',
                headers:
                    finalOptions?.body instanceof FormData
                        ? withCsrfHeaders(method, finalOptions?.headers)
                        : withCsrfHeaders(method, {
                            "Content-Type": "application/json",
                            ...(finalOptions?.headers ?? {}),
                        }),
                signal: controller.signal,
            });

            if (res.status === 401) {
                handleUnauthorized();
                return null;
            }

            const result = await res.json();
            if (!res.ok) {
                console.error(`Error fetching data from ${finalUrl}:`, {
                    status: res.status,
                    statusText: res.statusText,
                    error: result?.error || result
                });
            }

            setData(result);
            return result;
        } catch (e) {
            if (e instanceof DOMException && e.name === "AbortError") {
                return null;
            }
            const errorMessage = e instanceof Error ? e.message : "Unknown error";
            setError(errorMessage);
            throw e;
        } finally {
            if (controllerRef.current === controller) {
                setLoading(false);
            }
        }
    }, [url, optionsString]);

    // Auto-fetch using execute
    useEffect(() => {
        if (!url || !enabled) return;

        // Fetch data on mount
        execute(url, options);

        return () => {
            if (controllerRef.current) {
                controllerRef.current.abort();
            }
        };
    }, [url, enabled, optionsString]);

    return { data, error, loading, reset, execute };
}
