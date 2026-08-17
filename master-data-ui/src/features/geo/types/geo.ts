export type GeoLevel = {
  level_id: string;
  level_mnemonic: string;
  parent_level_id: string | null;
  display_name?: string | null;
  display_name_i18n?: Record<string, unknown> | null;
  version?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
};

export type GeoLevelValue = {
  level_value_id: string;
  level_id: string;
  level_value_mnemonic: string;
  parent_level_value_id?: string | null;
  pcode?: string | null;
  pcode_source?: string | null;
  boundary_uri?: string | null;
  boundary_simplified_uri?: string | null;
  display_name?: string | null;
  display_name_i18n?: Record<string, unknown> | null;
  version?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
};

export type GeoBreadcrumbItem = {
  id: string;
  label: string;
  levelId: string;
  /** Virtual root-level node (e.g. "Region") vs a concrete value. */
  kind: "level" | "value";
};

export type GeoTreeNode = {
  /** Unique tree key */
  key: string;
  kind: "level" | "value";
  levelId: string;
  value?: GeoLevelValue;
  label: string;
  parentKey: string | null;
  path: GeoBreadcrumbItem[];
  hasChildren: boolean;
};

export type ChildrenCacheEntry = {
  values: GeoLevelValue[];
  loading: boolean;
  error: string | null;
  loaded: boolean;
};
