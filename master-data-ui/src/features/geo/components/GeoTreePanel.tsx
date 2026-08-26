"use client";

import { useEffect, useMemo, useRef } from "react";
import { ChevronDown, ChevronRight, LoaderCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ChildrenCacheEntry, GeoTreeNode } from "../types";

type GeoTreePanelProps = {
  nodes: GeoTreeNode[];
  expandedKeys: Set<string>;
  selectedKey: string | null;
  childrenCache: Record<string, ChildrenCacheEntry>;
  getCacheKeysForNode: (node: GeoTreeNode) => string[];
  searchQuery: string;
  onToggle: (node: GeoTreeNode) => void;
  onSelect: (node: GeoTreeNode) => void;
};

function matchesSearch(node: GeoTreeNode, query: string): boolean {
  if (!query) return true;
  return node.label.toLowerCase().includes(query);
}

export default function GeoTreePanel({
  nodes,
  expandedKeys,
  selectedKey,
  childrenCache,
  getCacheKeysForNode,
  searchQuery,
  onToggle,
  onSelect,
}: GeoTreePanelProps) {
  const t = useTranslations();
  const listRef = useRef<HTMLDivElement>(null);
  const query = searchQuery.trim().toLowerCase();

  const childrenByParent = useMemo(() => {
    const map = new Map<string | null, GeoTreeNode[]>();
    for (const node of nodes) {
      const list = map.get(node.parentKey) ?? [];
      list.push(node);
      map.set(node.parentKey, list);
    }
    return map;
  }, [nodes]);

  const hasMatchingDescendant = useMemo(() => {
    const cache = new Map<string, boolean>();

    const check = (nodeKey: string): boolean => {
      if (cache.has(nodeKey)) return cache.get(nodeKey)!;
      const children = childrenByParent.get(nodeKey) ?? [];
      for (const child of children) {
        if (matchesSearch(child, query) || check(child.key)) {
          cache.set(nodeKey, true);
          return true;
        }
      }
      cache.set(nodeKey, false);
      return false;
    };

    return check;
  }, [childrenByParent, query]);

  const visibleNodes = useMemo(() => {
    const result: Array<{ node: GeoTreeNode; depth: number }> = [];

    const walk = (node: GeoTreeNode, depth: number) => {
      const selfMatch = matchesSearch(node, query);
      const descendantMatch = query ? hasMatchingDescendant(node.key) : false;
      if (query && !selfMatch && !descendantMatch) return;

      result.push({ node, depth });

      const expanded = expandedKeys.has(node.key) || (Boolean(query) && descendantMatch);
      if (!expanded) return;

      const cacheKeys = getCacheKeysForNode(node);
      const cacheLoading = cacheKeys.some(
        (cacheKey) => childrenCache[cacheKey]?.loading
      );
      const children = childrenByParent.get(node.key) ?? [];

      if (cacheLoading && children.length === 0) {
        result.push({
          node: {
            key: `${node.key}__loading`,
            kind: "value",
            levelId: node.levelId,
            label: t("loading"),
            parentKey: node.key,
            path: node.path,
            hasChildren: false,
          },
          depth: depth + 1,
        });
        return;
      }

      for (const child of children) {
        walk(child, depth + 1);
      }
    };

    for (const root of childrenByParent.get(null) ?? []) {
      walk(root, 0);
    }

    return result;
  }, [
    childrenByParent,
    childrenCache,
    expandedKeys,
    getCacheKeysForNode,
    hasMatchingDescendant,
    query,
    t,
  ]);

  const flatSelectable = useMemo(
    () => visibleNodes.filter((item) => !item.node.key.endsWith("__loading")),
    [visibleNodes]
  );

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (
        !["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Enter"].includes(
          event.key
        )
      ) {
        return;
      }
      event.preventDefault();

      const index = flatSelectable.findIndex(
        (item) => item.node.key === selectedKey
      );
      const current = index >= 0 ? flatSelectable[index]?.node : null;

      if (event.key === "ArrowDown") {
        const next =
          flatSelectable[
            Math.min(flatSelectable.length - 1, Math.max(0, index + 1))
          ];
        if (next) onSelect(next.node);
        return;
      }
      if (event.key === "ArrowUp") {
        const prev = flatSelectable[Math.max(0, index <= 0 ? 0 : index - 1)];
        if (prev) onSelect(prev.node);
        return;
      }
      if (!current) return;

      if (event.key === "Enter") {
        onSelect(current);
        return;
      }
      if (event.key === "ArrowRight") {
        if (current.hasChildren && !expandedKeys.has(current.key)) {
          onToggle(current);
        } else {
          const next = flatSelectable[index + 1];
          if (next) onSelect(next.node);
        }
        return;
      }
      if (event.key === "ArrowLeft") {
        if (expandedKeys.has(current.key)) {
          onToggle(current);
        } else if (current.parentKey) {
          const parent = nodes.find((n) => n.key === current.parentKey);
          if (parent) onSelect(parent);
        }
      }
    };

    el.addEventListener("keydown", onKeyDown);
    return () => el.removeEventListener("keydown", onKeyDown);
  }, [expandedKeys, flatSelectable, nodes, onSelect, onToggle, selectedKey]);

  if (nodes.length === 0) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center px-4 text-[14px] text-gray-400">
        {t("geo_no_levels")}
      </div>
    );
  }

  return (
    <div
      ref={listRef}
      tabIndex={0}
      role="tree"
      aria-label={t("geo_hierarchy")}
      className="h-full min-h-0 overflow-x-hidden overflow-y-auto px-2 py-2 outline-none focus-visible:ring-1 focus-visible:ring-(--color-yellow) [scrollbar-gutter:stable]"
    >
      {visibleNodes.length === 0 ? (
        <p className="px-2 py-6 text-center text-[13px] text-gray-400">
          {t("no_results")}
        </p>
      ) : (
        visibleNodes.map(({ node, depth }) => {
          if (node.key.endsWith("__loading")) {
            return (
              <div
                key={node.key}
                className="flex items-center gap-2 px-2 py-1.5 font-normal text-[16px] leading-none tracking-normal text-gray-400"
                style={{ paddingLeft: 8 + depth * 16 }}
              >
                <LoaderCircle size={14} className="animate-spin" />
                {t("loading")}
              </div>
            );
          }

          const expanded = expandedKeys.has(node.key);
          const selected = selectedKey === node.key;
          const cacheKeys = getCacheKeysForNode(node);
          const cacheEntries = cacheKeys.map((cacheKey) => childrenCache[cacheKey]);
          const cacheLoading = cacheEntries.some((entry) => entry?.loading);
          const loadedEntries = cacheEntries.filter((entry) => entry?.loaded);
          const count =
            cacheKeys.length === 0
              ? 0
              : loadedEntries.length === cacheKeys.length
                ? loadedEntries.reduce(
                    (sum, entry) => sum + (entry?.values.length ?? 0),
                    0
                  )
                : null;

          return (
            <div
              key={node.key}
              role="treeitem"
              aria-expanded={node.hasChildren ? expanded : undefined}
              aria-selected={selected}
              className={`group flex w-full items-center gap-1 rounded px-1 py-1.5 font-normal text-[16px] leading-none tracking-normal ${
                selected
                  ? "bg-(--color-yellow)/20 text-(--color-yellow)"
                  : "text-black hover:bg-gray-100"
              }`}
              style={{ paddingLeft: 4 + depth * 14 }}
            >
              <button
                type="button"
                className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded text-gray-600 hover:bg-gray-200 disabled:opacity-0"
                disabled={!node.hasChildren}
                aria-label={expanded ? t("collapse") : t("expand")}
                onClick={(event) => {
                  event.stopPropagation();
                  onToggle(node);
                }}
              >
                {cacheLoading ? (
                  <LoaderCircle size={16} className="animate-spin" />
                ) : expanded ? (
                  <ChevronDown size={16} />
                ) : (
                  <ChevronRight size={16} />
                )}
              </button>

              <button
                type="button"
                className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-left"
                onClick={() => onSelect(node)}
              >
                <span className="truncate font-normal text-[16px] leading-none tracking-normal">
                  {node.label}
                </span>
                {count !== null && node.hasChildren ? (
                  <span className="shrink-0 font-normal text-[16px] leading-none tracking-normal text-gray-400">
                    ({count})
                  </span>
                ) : null}
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}
