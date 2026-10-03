"use client";

import { useCallback, useMemo } from "react";
import { useAuth } from "@/context/Authcontext";
import { useCatalogueQuery } from "./api";
import type { CatalogueConfig, VersionInfo } from "./types";

const EMPTY = {};

/** `get_catalogue_config`: approval mode, boundary store, current geography version. */
export function useCatalogueConfig() {
    const { data, loading, error } = useCatalogueQuery<CatalogueConfig>("get_catalogue_config", EMPTY);
    return { config: data ?? null, loading, error };
}

/**
 * Whether the signed-in user made the given version (created, last edited or submitted it).
 * The backend's maker ≠ checker rule compares the stable user id — the JWT `sub` claim
 * (fallback `preferred_username`, then `name`) — with created_by / updated_by / submitted_by
 * (which hold ids; the `*_by_name` fields are only for display); the UI hides approve/reject
 * for the maker and the backend still enforces the rule (G2P-CAT-403).
 */
export function useIsMaker() {
    const { user } = useAuth();
    const ids = useMemo(() => {
        const u = (user ?? {}) as Record<string, unknown>;
        return new Set(
            [u.name, u.preferred_username, u.sub, u.email, u.user_name, u.username]
                .filter((v): v is string => typeof v === "string" && v.trim() !== "")
                .map((v) => v.trim().toLowerCase()),
        );
    }, [user]);

    return useCallback(
        (version: VersionInfo | null | undefined) => {
            if (!version || ids.size === 0) return false;
            return [version.created_by, version.updated_by, version.submitted_by].some(
                (m) => typeof m === "string" && ids.has(m.trim().toLowerCase()),
            );
        },
        [ids],
    );
}
