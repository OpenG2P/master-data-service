import { useFetch } from "@/shared/hooks/useFetch";
import type { AttributeValue } from "../types";

export function valueHasChildren(
    valueId: string,
    values: AttributeValue[],
): boolean {
    return values.some((v) => v.parent_value_id === valueId);
}

export function useAttributeValues(
    attributeId?: string,
    parentValueId?: string | null,
    searchText?: string,
) {
    const { data, loading, error, execute } = useFetch<{
        attributeValues: AttributeValue[];
        total?: number;
    }>({
        url: "/api/attributes/get-attribute-values",
        enabled: !!attributeId,
        options: {
            method: "POST",
            body: JSON.stringify({
                attribute_id: attributeId,
            }),
        },
    });

    const allValues = data?.attributeValues ?? [];

    const isRoot = !parentValueId;
    const filtered = allValues.filter((v) => {
        const parentMatch = isRoot
            ? v.parent_value_id === null || v.parent_value_id === ""
            : v.parent_value_id === parentValueId;
        if (!parentMatch) return false;
        if (searchText?.trim()) {
            const q = searchText.trim().toLowerCase();
            return (
                v.value_code?.toLowerCase().includes(q) ||
                v.value_display?.toLowerCase().includes(q)
            );
        }
        return true;
    });

    return {
        attributeValues: filtered,
        allValues,
        total: data?.total ?? 0,
        loading,
        error,
        refresh: execute,
    };
}
