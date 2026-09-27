import type { GeoLevel, GeoLevelValue } from "../types";

export function getRootLevels(levels: GeoLevel[]): GeoLevel[] {
  return levels.filter((level) => !level.parent_level_id);
}

export function getChildLevels(
  levels: GeoLevel[],
  parentLevelId: string
): GeoLevel[] {
  return levels.filter((level) => level.parent_level_id === parentLevelId);
}

/** First child level only. Prefer getChildLevels when a parent may fork. */
export function getChildLevel(
  levels: GeoLevel[],
  parentLevelId: string
): GeoLevel | undefined {
  return getChildLevels(levels, parentLevelId)[0];
}

export function getLevelById(
  levels: GeoLevel[],
  levelId: string
): GeoLevel | undefined {
  return levels.find((level) => level.level_id === levelId);
}

export function getLevelDepth(levels: GeoLevel[], levelId: string): number {
  let depth = 0;
  let current = getLevelById(levels, levelId);
  const seen = new Set<string>();
  while (current?.parent_level_id && !seen.has(current.level_id)) {
    seen.add(current.level_id);
    depth += 1;
    current = getLevelById(levels, current.parent_level_id);
  }
  return depth;
}

/** Depth-first from each root so forked child levels are all included. */
export function orderGeoLevelsByHierarchy(levels: GeoLevel[]): GeoLevel[] {
  const result: GeoLevel[] = [];
  const visited = new Set<string>();

  const walk = (level: GeoLevel) => {
    if (visited.has(level.level_id)) return;
    visited.add(level.level_id);
    result.push(level);
    for (const child of getChildLevels(levels, level.level_id)) {
      walk(child);
    }
  };

  for (const root of getRootLevels(levels)) {
    walk(root);
  }

  for (const level of levels) {
    if (!visited.has(level.level_id)) {
      result.push(level);
    }
  }

  return result;
}

export function getLevelLabel(level: GeoLevel | undefined, fallback = "Level"): string {
  if (!level) return fallback;
  return level.level_mnemonic || level.level_id;
}

export function getValueLabel(value: GeoLevelValue | undefined, fallback = "—"): string {
  if (!value) return fallback;
  return value.level_value_mnemonic || value.level_value_id;
}

export function childrenCacheKey(
  levelId: string,
  parentLevelValueId?: string | null
): string {
  return `${levelId}::${parentLevelValueId ?? ""}`;
}

export function levelNodeKey(levelId: string): string {
  return `level:${levelId}`;
}

export function valueNodeKey(levelValueId: string): string {
  return `value:${levelValueId}`;
}

export function titleCaseFromMnemonic(mnemonic: string): string {
  return mnemonic
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
