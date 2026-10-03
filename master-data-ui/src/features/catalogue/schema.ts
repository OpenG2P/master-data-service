import type { JsonSchema } from "./types";

export interface SchemaProperty {
    name: string;
    schema: Record<string, unknown>;
    required: boolean;
}

function isObject(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Top-level properties of an attribute schema, in declaration order. */
export function schemaProperties(schema: JsonSchema | null | undefined): SchemaProperty[] {
    if (!isObject(schema) || !isObject(schema.properties)) return [];
    const required = new Set(Array.isArray(schema.required) ? schema.required.map(String) : []);
    return Object.entries(schema.properties)
        .filter(([, s]) => isObject(s))
        .map(([name, s]) => ({ name, schema: s as Record<string, unknown>, required: required.has(name) }));
}

/** `x-list-ref` of a property or of its array items. */
export function listRefOf(prop: Record<string, unknown>): { ref: string; multiple: boolean } | null {
    if (typeof prop["x-list-ref"] === "string" && prop["x-list-ref"]) {
        return { ref: prop["x-list-ref"] as string, multiple: false };
    }
    const items = prop.items;
    if (prop.type === "array" && isObject(items) && typeof items["x-list-ref"] === "string" && items["x-list-ref"]) {
        return { ref: items["x-list-ref"] as string, multiple: true };
    }
    return null;
}

const JSON_TYPES = new Set(["string", "number", "integer", "boolean", "object", "array", "null"]);

function collectRefs(node: unknown, path: string, out: { path: string; ref: unknown }[]) {
    if (!isObject(node)) return;
    if ("x-list-ref" in node) out.push({ path, ref: node["x-list-ref"] });
    if (isObject(node.properties)) {
        for (const [k, v] of Object.entries(node.properties)) collectRefs(v, `${path}.${k}`, out);
    }
    if (isObject(node.items)) collectRefs(node.items, `${path}[]`, out);
}

/**
 * Light client-side checks of an attribute schema (the backend validates it fully as JSON Schema
 * 2020-12 on update / submit). `knownLists` are list codes; unknown `x-list-ref` targets are errors.
 */
export interface SchemaIssue {
    /** i18n key (cat_schema_err_*). */
    key: string;
    values?: Record<string, string>;
}

export function validateAttributeSchema(schema: unknown, knownLists: string[]): SchemaIssue[] {
    const errors: SchemaIssue[] = [];
    if (!isObject(schema)) return [{ key: "cat_schema_err_not_object" }];
    if (schema.type !== undefined && schema.type !== "object") {
        errors.push({ key: "cat_schema_err_top_type" });
    }
    if (schema.properties !== undefined && !isObject(schema.properties)) {
        errors.push({ key: "cat_schema_err_properties" });
    }
    const props = isObject(schema.properties) ? schema.properties : {};
    for (const [name, prop] of Object.entries(props)) {
        if (!isObject(prop)) {
            errors.push({ key: "cat_schema_err_property", values: { name } });
            continue;
        }
        const type = prop.type;
        const types = Array.isArray(type) ? type : type === undefined ? [] : [type];
        for (const ty of types) {
            if (typeof ty !== "string" || !JSON_TYPES.has(ty))
                errors.push({ key: "cat_schema_err_type", values: { name, type: JSON.stringify(ty) } });
        }
        if (prop.enum !== undefined && !Array.isArray(prop.enum))
            errors.push({ key: "cat_schema_err_enum", values: { name } });
    }
    if (schema.required !== undefined) {
        if (!Array.isArray(schema.required) || schema.required.some((r) => typeof r !== "string")) {
            errors.push({ key: "cat_schema_err_required" });
        } else {
            for (const r of schema.required as string[]) {
                if (!(r in props)) errors.push({ key: "cat_schema_err_required_unknown", values: { name: r } });
            }
        }
    }
    const refs: { path: string; ref: unknown }[] = [];
    collectRefs(schema, "$", refs);
    const known = new Set(knownLists.map((c) => c.toUpperCase()));
    for (const { path, ref } of refs) {
        if (typeof ref !== "string" || !ref.trim()) {
            errors.push({ key: "cat_schema_err_ref", values: { path } });
        } else if (known.size > 0 && !known.has(ref.toUpperCase())) {
            errors.push({ key: "cat_schema_err_ref_unknown", values: { path, ref } });
        }
    }
    return errors;
}

export const EXAMPLE_ATTRIBUTE_SCHEMA = {
    type: "object",
    properties: {
        crop: { type: "string", "x-list-ref": "CROP_COMMODITY", description: "Crop this value applies to" },
        min_area_ha: { type: "number", minimum: 0 },
        irrigated: { type: "boolean" },
    },
    required: ["crop"],
    additionalProperties: false,
};
