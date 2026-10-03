export type GeoLevel = {
  level_id: string;
  level_mnemonic: string;
  parent_level_id: string | null;
  display?: string | null;
  display_i18n?: Record<string, string> | null;
};

export type GeoLevelValue = {
  level_value_id: string;
  level_id: string;
  level_value_mnemonic: string;
  parent_level_value_id?: string | null;
  /** Catalogue fields (geography versions): status and labels per locale. */
  status?: string;
  name_i18n?: Record<string, string> | null;
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
