import type { GeoLevel, GeoLevelValue } from "../types";

export function orderGeoLevelsByHierarchy(levels: GeoLevel[]): GeoLevel[] {
  const result: GeoLevel[] = [];
  const visited = new Set<string>();
  let current = levels.find((level) => !level.parent_level_id);

  while (current && !visited.has(current.level_id)) {
    visited.add(current.level_id);
    result.push(current);
    current = levels.find((level) => level.parent_level_id === current!.level_id);
  }

  // Append any disconnected levels so nothing is silently dropped.
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

export function getChildLevel(
  levels: GeoLevel[],
  parentLevelId: string
): GeoLevel | undefined {
  return levels.find((level) => level.parent_level_id === parentLevelId);
}

export function getRootLevels(levels: GeoLevel[]): GeoLevel[] {
  return levels.filter((level) => !level.parent_level_id);
}

export function getLevelById(
  levels: GeoLevel[],
  levelId: string
): GeoLevel | undefined {
  return levels.find((level) => level.level_id === levelId);
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
