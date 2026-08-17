export interface Attribute {
    attribute_id: string;
    attribute_code: string;
    attribute_display: string;
    is_hierarchical: boolean;
}

export interface AttributeValue {
    value_id: string;
    attribute_id: string;
    value_code: string;
    value_display: string;
    parent_value_id: string | null;
    sort_order: number;
}

export interface PaginationMeta {
    number_of_items: number;
    number_of_pages: number;
}
