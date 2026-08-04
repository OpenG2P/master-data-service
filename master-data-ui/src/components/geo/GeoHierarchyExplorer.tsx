"use client";

import LoadingState from "@/components/LoadingState";
import GeoChildrenTable from "@/components/geo/GeoChildrenTable";
import GeoLevelDialog from "@/components/geo/GeoLevelDialog";
import GeoNodeDialog, {
  type GeoNodeDialogField,
} from "@/components/geo/GeoNodeDialog";
import GeoTreePanel from "@/components/geo/GeoTreePanel";
import { useAuth } from "@/context/Authcontext";
import { fetchGeoLevels, fetchGeoLevelValues } from "@/shared/api/geo";
import {
  childrenCacheKey,
  getChildLevel,
  getLevelById,
  getLevelLabel,
  getRootLevels,
  getValueLabel,
  levelNodeKey,
  orderGeoLevelsByHierarchy,
  valueNodeKey,
} from "@/shared/utils/geoHierarchy";
import type {
  ChildrenCacheEntry,
  GeoBreadcrumbItem,
  GeoLevel,
  GeoLevelValue,
  GeoTreeNode,
} from "@/types/geo";
import { ArrowLeft, MapPin, Menu, Search, X } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

type DialogState =
  | {
      open: true;
      mode: "add" | "edit";
      title: string;
      contextFields: GeoNodeDialogField[];
      nameLabel: string;
      codeLabel: string;
      initialName?: string;
      initialCode?: string;
    }
  | { open: false };

function subscribeViewport(callback: () => void) {
  window.addEventListener("resize", callback);
  return () => window.removeEventListener("resize", callback);
}

function getViewportSnapshot() {
  return window.innerWidth;
}

function getServerViewportSnapshot() {
  return 1440;
}

function useViewportWidth() {
  return useSyncExternalStore(
    subscribeViewport,
    getViewportSnapshot,
    getServerViewportSnapshot
  );
}

export default function GeoHierarchyExplorer() {
  const t = useTranslations();
  const { handleUnauthorized } = useAuth();
  const width = useViewportWidth();
  const isDesktop = width > 1200;
  const isTablet = width >= 768 && width <= 1200;
  const isMobile = width < 768;

  const [levels, setLevels] = useState<GeoLevel[]>([]);
  const [levelsLoading, setLevelsLoading] = useState(true);
  const [levelsError, setLevelsError] = useState<string | null>(null);

  const [nodesByKey, setNodesByKey] = useState<Record<string, GeoTreeNode>>(
    {}
  );
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [childrenCache, setChildrenCache] = useState<
    Record<string, ChildrenCacheEntry>
  >({});
  const [searchQuery, setSearchQuery] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [mobileShowDetails, setMobileShowDetails] = useState(false);
  const [dialog, setDialog] = useState<DialogState>({ open: false });
  const [levelDialogOpen, setLevelDialogOpen] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [breadcrumbMoreOpen, setBreadcrumbMoreOpen] = useState(false);

  const childrenCacheRef = useRef(childrenCache);
  const nodesByKeyRef = useRef(nodesByKey);
  const levelsRef = useRef(levels);
  const childrenAbortRef = useRef<Map<string, AbortController>>(new Map());
  const childrenInflightRef = useRef<
    Map<string, Promise<ChildrenCacheEntry | undefined>>
  >(new Map());
  const levelsAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    childrenCacheRef.current = childrenCache;
  }, [childrenCache]);

  useEffect(() => {
    nodesByKeyRef.current = nodesByKey;
  }, [nodesByKey]);

  useEffect(() => {
    levelsRef.current = levels;
  }, [levels]);

  const orderedLevels = useMemo(
    () => orderGeoLevelsByHierarchy(levels),
    [levels]
  );

  const nodes = useMemo(() => Object.values(nodesByKey), [nodesByKey]);
  const selected = selectedKey ? (nodesByKey[selectedKey] ?? null) : null;

  const materializeChildren = useCallback(
    (
      parentNode: GeoTreeNode,
      values: GeoLevelValue[],
      valueLevelId: string,
      levelList: GeoLevel[]
    ) => {
      const childLevel = getChildLevel(levelList, valueLevelId);
      setNodesByKey((prev) => {
        const next = { ...prev };
        for (const key of Object.keys(next)) {
          if (next[key]?.parentKey === parentNode.key) {
            delete next[key];
          }
        }

        for (const value of values) {
          const key = valueNodeKey(value.level_value_id);
          next[key] = {
            key,
            kind: "value",
            levelId: value.level_id,
            value,
            label: getValueLabel(value),
            parentKey: parentNode.key,
            path: [
              ...parentNode.path,
              {
                id: value.level_value_id,
                label: getValueLabel(value),
                levelId: value.level_id,
                kind: "value",
              },
            ],
            hasChildren: Boolean(childLevel),
          };
        }
        nodesByKeyRef.current = next;
        return next;
      });
    },
    []
  );

  const ensureChildren = useCallback(
    async (
      levelId: string,
      parentLevelValueId: string,
      force = false
    ): Promise<ChildrenCacheEntry | undefined> => {
      const cacheKey = childrenCacheKey(levelId, parentLevelValueId);
      const existing = childrenCacheRef.current[cacheKey];
      if (!force && existing?.loaded) {
        return existing;
      }

      const inflight = childrenInflightRef.current.get(cacheKey);
      if (!force && inflight) {
        return inflight;
      }

      childrenAbortRef.current.get(cacheKey)?.abort();
      const controller = new AbortController();
      childrenAbortRef.current.set(cacheKey, controller);

      setChildrenCache((prev) => {
        const next = {
          ...prev,
          [cacheKey]: {
            values: prev[cacheKey]?.values ?? [],
            loading: true,
            error: null,
            loaded: false,
          },
        };
        childrenCacheRef.current = next;
        return next;
      });

      const request = (async () => {
        try {
          const values = await fetchGeoLevelValues({
            levelId,
            parentLevelValueId,
            signal: controller.signal,
          });
          const entry: ChildrenCacheEntry = {
            values,
            loading: false,
            error: null,
            loaded: true,
          };
          setChildrenCache((prev) => {
            const next = { ...prev, [cacheKey]: entry };
            childrenCacheRef.current = next;
            return next;
          });
          return entry;
        } catch (error) {
          if (error instanceof DOMException && error.name === "AbortError") {
            return childrenCacheRef.current[cacheKey];
          }
          if (error instanceof Error && error.message === "UNAUTHORIZED") {
            handleUnauthorized();
            return childrenCacheRef.current[cacheKey];
          }
          const message =
            error instanceof Error ? error.message : t("geo_load_error");
          const entry: ChildrenCacheEntry = {
            values: [],
            loading: false,
            error: message,
            loaded: false,
          };
          setChildrenCache((prev) => {
            const next = { ...prev, [cacheKey]: entry };
            childrenCacheRef.current = next;
            return next;
          });
          return entry;
        } finally {
          childrenInflightRef.current.delete(cacheKey);
        }
      })();

      childrenInflightRef.current.set(cacheKey, request);
      return request;
    },
    [handleUnauthorized, t]
  );

  const getFetchTargetForNode = useCallback(
    (
      node: GeoTreeNode,
      levelList: GeoLevel[] = levelsRef.current
    ): { levelId: string; parentValueId: string } | null => {
      if (node.kind === "level") {
        return { levelId: node.levelId, parentValueId: "" };
      }
      const childLevel = getChildLevel(levelList, node.levelId);
      if (!childLevel || !node.value) return null;
      return {
        levelId: childLevel.level_id,
        parentValueId: node.value.level_value_id,
      };
    },
    []
  );

  const getCacheKeyForNode = useCallback(
    (node: GeoTreeNode) => {
      const target = getFetchTargetForNode(node);
      if (!target) return null;
      return childrenCacheKey(target.levelId, target.parentValueId);
    },
    [getFetchTargetForNode]
  );

  const loadNodeChildren = useCallback(
    async (node: GeoTreeNode, force = false) => {
      const levelList = levelsRef.current;
      const target = getFetchTargetForNode(node, levelList);
      if (!target) return;
      const entry = await ensureChildren(
        target.levelId,
        target.parentValueId,
        force
      );
      if (entry?.loaded) {
        materializeChildren(node, entry.values, target.levelId, levelList);
      }
    },
    [ensureChildren, getFetchTargetForNode, materializeChildren]
  );

  const loadLevels = useCallback(async () => {
    levelsAbortRef.current?.abort();
    const controller = new AbortController();
    levelsAbortRef.current = controller;

    setLevelsLoading(true);
    setLevelsError(null);
    setBanner(null);

    try {
      const data = await fetchGeoLevels(controller.signal);
      const ordered = orderGeoLevelsByHierarchy(data);
      setLevels(ordered);
      levelsRef.current = ordered;

      const roots = getRootLevels(ordered);
      const nextNodes: Record<string, GeoTreeNode> = {};
      const nextExpanded = new Set<string>();

      for (const root of roots) {
        const key = levelNodeKey(root.level_id);
        const label = getLevelLabel(root);
        nextNodes[key] = {
          key,
          kind: "level",
          levelId: root.level_id,
          label,
          parentKey: null,
          path: [
            {
              id: root.level_id,
              label,
              levelId: root.level_id,
              kind: "level",
            },
          ],
          hasChildren: true,
        };
        nextExpanded.add(key);
      }

      setNodesByKey(nextNodes);
      nodesByKeyRef.current = nextNodes;
      setExpandedKeys(nextExpanded);
      setChildrenCache({});
      childrenCacheRef.current = {};
      childrenInflightRef.current.clear();
      childrenAbortRef.current.forEach((c) => c.abort());
      childrenAbortRef.current.clear();
      setSelectedKey(roots[0] ? levelNodeKey(roots[0].level_id) : null);
      setMobileShowDetails(false);

      for (const root of roots) {
        const parentNode = nextNodes[levelNodeKey(root.level_id)];
        if (!parentNode) continue;
        const entry = await ensureChildren(root.level_id, "", true);
        if (entry?.loaded) {
          materializeChildren(
            parentNode,
            entry.values,
            root.level_id,
            ordered
          );
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (error instanceof Error && error.message === "UNAUTHORIZED") {
        handleUnauthorized();
        return;
      }
      setLevelsError(
        error instanceof Error ? error.message : t("geo_load_error")
      );
    } finally {
      setLevelsLoading(false);
    }
  }, [ensureChildren, handleUnauthorized, materializeChildren, t]);

  useEffect(() => {
    void loadLevels();
    return () => {
      levelsAbortRef.current?.abort();
      childrenAbortRef.current.forEach((c) => c.abort());
    };
    // Bootstrap once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleToggle = useCallback(
    (node: GeoTreeNode) => {
      setExpandedKeys((prev) => {
        const next = new Set(prev);
        if (next.has(node.key)) {
          next.delete(node.key);
        } else {
          next.add(node.key);
          void loadNodeChildren(node);
        }
        return next;
      });
    },
    [loadNodeChildren]
  );

  const handleSelect = useCallback(
    (node: GeoTreeNode) => {
      setSelectedKey(node.key);
      setBanner(null);
      if (isMobile) setMobileShowDetails(true);
      if (isTablet) setDrawerOpen(false);
      void loadNodeChildren(node);
    },
    [isMobile, isTablet, loadNodeChildren]
  );

  const selectedChildrenEntry = useMemo(() => {
    if (!selected) return undefined;
    const cacheKey = getCacheKeyForNode(selected);
    return cacheKey ? childrenCache[cacheKey] : undefined;
  }, [childrenCache, getCacheKeyForNode, selected]);

  // Prefetch each row's child list so table/tree counts populate without expanding.
  useEffect(() => {
    if (!selectedChildrenEntry?.loaded) return;
    for (const value of selectedChildrenEntry.values) {
      const childLevel = getChildLevel(orderedLevels, value.level_id);
      if (!childLevel) continue;
      void ensureChildren(childLevel.level_id, value.level_value_id);
    }
  }, [ensureChildren, orderedLevels, selectedChildrenEntry]);

  const handleBreadcrumbClick = useCallback(
    (item: GeoBreadcrumbItem) => {
      const key =
        item.kind === "level" ? levelNodeKey(item.id) : valueNodeKey(item.id);
      const node = nodesByKeyRef.current[key];
      if (node) handleSelect(node);
    },
    [handleSelect]
  );

  const handleRootBreadcrumb = useCallback(() => {
    const roots = getRootLevels(orderedLevels);
    const root = roots[0];
    if (!root) {
      setSelectedKey(null);
      if (isMobile) setMobileShowDetails(false);
      return;
    }
    const node = nodesByKeyRef.current[levelNodeKey(root.level_id)];
    if (node) {
      handleSelect(node);
    } else {
      setSelectedKey(levelNodeKey(root.level_id));
    }
    if (isMobile) setMobileShowDetails(false);
  }, [handleSelect, isMobile, orderedLevels]);

  /** Keep breadcrumb compact: first + last 2 when path is deep. */
  const breadcrumbSegments = useMemo(() => {
    const path = selected?.path ?? [];
    if (path.length <= 3) {
      return { head: path, collapsed: [] as GeoBreadcrumbItem[], tail: [] as GeoBreadcrumbItem[] };
    }
    return {
      head: path.slice(0, 1),
      collapsed: path.slice(1, -2),
      tail: path.slice(-2),
    };
  }, [selected?.path]);

  useEffect(() => {
    setBreadcrumbMoreOpen(false);
  }, [selected?.key]);

  const buildChildNode = useCallback(
    (parent: GeoTreeNode, value: GeoLevelValue): GeoTreeNode => {
      const key = valueNodeKey(value.level_value_id);
      return {
        key,
        kind: "value",
        levelId: value.level_id,
        value,
        label: getValueLabel(value),
        parentKey: parent.key,
        path: [
          ...parent.path,
          {
            id: value.level_value_id,
            label: getValueLabel(value),
            levelId: value.level_id,
            kind: "value",
          },
        ],
        hasChildren: Boolean(
          getChildLevel(levelsRef.current, value.level_id)
        ),
      };
    },
    []
  );

  const handleSelectChild = useCallback(
    (value: GeoLevelValue) => {
      if (!selected) return;
      const key = valueNodeKey(value.level_value_id);
      let node = nodesByKeyRef.current[key];
      if (!node) {
        node = buildChildNode(selected, value);
        setNodesByKey((prev) => {
          const next = { ...prev, [key]: node! };
          nodesByKeyRef.current = next;
          return next;
        });
      }
      setExpandedKeys((prev) => new Set(prev).add(selected.key));
      handleSelect(node);
    },
    [buildChildNode, handleSelect, selected]
  );

  const getChildCount = useCallback(
    (value: GeoLevelValue) => {
      const childLevel = getChildLevel(orderedLevels, value.level_id);
      if (!childLevel) return 0;
      const entry =
        childrenCache[
          childrenCacheKey(childLevel.level_id, value.level_value_id)
        ];
      if (!entry?.loaded) return null;
      return entry.values.length;
    },
    [childrenCache, orderedLevels]
  );

  const openAddDialog = useCallback(
    (parentNode: GeoTreeNode | null, asRoot = false) => {
      const root = getRootLevels(orderedLevels)[0];
      if (!root) return;

      if (asRoot || !parentNode || parentNode.kind === "level") {
        const level =
          parentNode?.kind === "level"
            ? (getLevelById(orderedLevels, parentNode.levelId) ?? root)
            : root;
        setDialog({
          open: true,
          mode: "add",
          title: t("geo_add_named", { name: getLevelLabel(level) }),
          contextFields: [],
          nameLabel: t("geo_name_field", { name: getLevelLabel(level) }),
          codeLabel: t("geo_code"),
        });
        return;
      }

      const childLevel = getChildLevel(orderedLevels, parentNode.levelId);
      if (!childLevel) return;

      setDialog({
        open: true,
        mode: "add",
        title: t("geo_add_named", { name: getLevelLabel(childLevel) }),
        contextFields: parentNode.path.map((item) => ({
          label:
            item.kind === "level"
              ? t("geo_level")
              : getLevelLabel(getLevelById(orderedLevels, item.levelId)),
          value: item.label,
          readOnly: true,
        })),
        nameLabel: t("geo_name_field", {
          name: getLevelLabel(childLevel),
        }),
        codeLabel: t("geo_code"),
      });
    },
    [orderedLevels, t]
  );

  const openEditDialog = useCallback(
    (node: GeoTreeNode) => {
      if (node.kind !== "value" || !node.value) return;
      const level = getLevelById(orderedLevels, node.levelId);
      setDialog({
        open: true,
        mode: "edit",
        title: t("geo_edit_named", { name: getLevelLabel(level) }),
        contextFields: node.path.slice(0, -1).map((item) => ({
          label:
            item.kind === "level"
              ? t("geo_level")
              : getLevelLabel(getLevelById(orderedLevels, item.levelId)),
          value: item.label,
          readOnly: true,
        })),
        nameLabel: t("geo_name_field", { name: getLevelLabel(level) }),
        codeLabel: t("geo_code"),
        initialName: getValueLabel(node.value),
        initialCode: node.value.pcode || node.value.level_value_mnemonic || "",
      });
    },
    [orderedLevels, t]
  );

  const treePanel = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-[#5A5A5A] px-4 py-2.5 text-start font-normal text-[16px] leading-none tracking-normal text-[#F4BB1B]">
        {t("geo_panel_hierarchy")}
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <GeoTreePanel
          nodes={nodes}
          expandedKeys={expandedKeys}
          selectedKey={selectedKey}
          childrenCache={childrenCache}
          getCacheKeyForNode={getCacheKeyForNode}
          searchQuery={searchQuery}
          onToggle={handleToggle}
          onSelect={handleSelect}
        />
      </div>
    </div>
  );

  const addLevelParentLabel = useMemo(() => {
    if (orderedLevels.length === 0) return null;
    // Prefer extending under the selected node's level; otherwise append under the deepest level.
    if (selected) {
      return getLevelLabel(getLevelById(orderedLevels, selected.levelId));
    }
    const deepest = orderedLevels[orderedLevels.length - 1];
    return getLevelLabel(deepest);
  }, [orderedLevels, selected]);

  // Only allow adding a level type when the focus level has no child level yet.
  const canAddLevel = useMemo(() => {
    if (orderedLevels.length === 0) return true;
    const focusLevelId = selected
      ? selected.levelId
      : orderedLevels[orderedLevels.length - 1]?.level_id;
    if (!focusLevelId) return true;
    return !getChildLevel(orderedLevels, focusLevelId);
  }, [orderedLevels, selected]);

  const addValueAction = useMemo(() => {
    if (orderedLevels.length === 0) return null;

    // Root / level context → add a root-level value
    if (!selected || selected.kind === "level") {
      const rootLevel =
        selected?.kind === "level"
          ? getLevelById(orderedLevels, selected.levelId)
          : getRootLevels(orderedLevels)[0];
      if (!rootLevel) return null;
      return {
        onClick: () =>
          openAddDialog(selected?.kind === "level" ? selected : null, true),
      };
    }

    // Value selected → add a child-level value
    const childLevel = getChildLevel(orderedLevels, selected.levelId);
    if (!childLevel) return null;
    return {
      onClick: () => openAddDialog(selected),
    };
  }, [openAddDialog, orderedLevels, selected]);

  const childrenPanel = (
    <GeoChildrenTable
      selected={selected}
      childrenEntry={selectedChildrenEntry}
      onSelect={handleSelectChild}
      onEdit={(value) => {
        if (!selected) return;
        const node =
          nodesByKeyRef.current[valueNodeKey(value.level_value_id)] ??
          buildChildNode(selected, value);
        openEditDialog(node);
      }}
      onDelete={() => setBanner(t("geo_write_unavailable"))}
      getChildCount={getChildCount}
      footerActions={
        <>
          <button
            type="button"
            disabled={!canAddLevel}
            onClick={() => {
              if (!canAddLevel) return;
              setLevelDialogOpen(true);
            }}
            className="inline-flex h-9 shrink-0 cursor-pointer items-center gap-2 rounded-[10px] bg-[#F4BB1B] px-4 text-[14px] font-semibold text-black disabled:cursor-not-allowed disabled:bg-white/15 disabled:text-white/40"
          >
            {t("geo_add_level")}
            <span className="flex h-[18px] w-[18px] items-center justify-center rounded-[10px] bg-white text-[14px] font-bold leading-none text-black disabled:bg-white/40">
              +
            </span>
          </button>
          {addValueAction ? (
            <button
              type="button"
              onClick={addValueAction.onClick}
              className="inline-flex h-9 shrink-0 cursor-pointer items-center gap-2 rounded-[10px] bg-[#F4BB1B] px-4 text-[14px] font-semibold text-black"
            >
              {t("geo_add_level_value")}
              <span className="flex h-[18px] w-[18px] items-center justify-center rounded-[10px] bg-white text-[14px] font-bold leading-none text-black">
                +
              </span>
            </button>
          ) : null}
        </>
      }
    />
  );

  if (levelsLoading) {
    return (
      <section className="flex min-h-0 flex-1 flex-col bg-black">
        <LoadingState compact />
      </section>
    );
  }

  if (levelsError) {
    return (
      <section className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 bg-black px-6 text-center text-white">
        <p className="text-[15px] text-red-300">{levelsError}</p>
        <button
          type="button"
          onClick={() => void loadLevels()}
          className="h-9 cursor-pointer rounded-[10px] bg-[#F4BB1B] px-4 text-[14px] font-semibold text-black"
        >
          {t("refresh")}
        </button>
      </section>
    );
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3 bg-black p-3 text-white sm:gap-4 sm:p-5">
      <div className="grid shrink-0 grid-cols-[6fr_4fr] items-center gap-3">
        <nav
          aria-label={t("geo_breadcrumb")}
          className="flex min-w-0 items-center gap-x-2 overflow-hidden font-normal text-[16px] leading-none tracking-normal"
        >
          {isMobile && mobileShowDetails ? (
            <button
              type="button"
              onClick={() => setMobileShowDetails(false)}
              className="mr-1 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded hover:bg-white/10"
              aria-label={t("back")}
            >
              <ArrowLeft size={16} />
            </button>
          ) : null}
          {isTablet ? (
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="mr-1 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded border border-[#5A5A5A] hover:bg-white/5"
              aria-label={t("geo_panel_hierarchy")}
            >
              <Menu size={16} />
            </button>
          ) : null}
          <button
            type="button"
            onClick={handleRootBreadcrumb}
            className={`inline-flex shrink-0 items-center gap-2 cursor-pointer hover:text-[#F4BB1B] hover:underline ${
              selected ? "font-normal text-white/70" : "text-white"
            }`}
          >
            <MapPin size={16} className="shrink-0 text-[#F4BB1B]" />
            {t("geo_locations")}
          </button>
          {[
            ...breadcrumbSegments.head.map((item) => ({
              item,
              kind: "crumb" as const,
            })),
            ...(breadcrumbSegments.collapsed.length > 0
              ? [{ kind: "more" as const }]
              : []),
            ...breadcrumbSegments.tail.map((item) => ({
              item,
              kind: "crumb" as const,
            })),
          ].map((segment, index, segments) => {
            if (segment.kind === "more") {
              return (
                <span
                  key="breadcrumb-more"
                  className="relative inline-flex shrink-0 items-center gap-2"
                >
                  <span className="text-white/40" aria-hidden>
                    &gt;
                  </span>
                  <button
                    type="button"
                    aria-expanded={breadcrumbMoreOpen}
                    aria-label={t("geo_breadcrumb_more")}
                    onClick={() => setBreadcrumbMoreOpen((open) => !open)}
                    className="cursor-pointer rounded px-1.5 font-normal text-white/70 hover:bg-white/10 hover:text-[#F4BB1B]"
                  >
                    …
                  </button>
                  {breadcrumbMoreOpen ? (
                    <>
                      <button
                        type="button"
                        className="fixed inset-0 z-20 cursor-default"
                        aria-label={t("close")}
                        onClick={() => setBreadcrumbMoreOpen(false)}
                      />
                      <ul className="absolute left-0 top-full z-30 mt-1 min-w-[12rem] max-w-[18rem] rounded border border-[#5A5A5A] bg-black py-1 shadow-lg">
                        {breadcrumbSegments.collapsed.map((item) => (
                          <li key={`${item.kind}-${item.id}`}>
                            <button
                              type="button"
                              title={item.label}
                              onClick={() => {
                                setBreadcrumbMoreOpen(false);
                                handleBreadcrumbClick(item);
                              }}
                              className="block w-full cursor-pointer truncate px-3 py-1.5 text-left text-[14px] font-medium text-white/80 hover:bg-white/10 hover:text-[#F4BB1B]"
                            >
                              {item.label}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                </span>
              );
            }

            const item = segment.item!;
            const isLast = index === segments.length - 1;
            return (
              <span
                key={`${item.kind}-${item.id}`}
                className="inline-flex min-w-0 items-center gap-2"
              >
                <span className="shrink-0 text-white/40" aria-hidden>
                  &gt;
                </span>
                {isLast ? (
                  <span className="min-w-0 truncate text-white" title={item.label}>
                    {item.label}
                  </span>
                ) : (
                  <button
                    type="button"
                    title={item.label}
                    onClick={() => handleBreadcrumbClick(item)}
                    className="min-w-0 max-w-[9rem] cursor-pointer truncate font-normal text-white/70 hover:text-[#F4BB1B] hover:underline"
                  >
                    {item.label}
                  </button>
                )}
              </span>
            );
          })}
        </nav>

        <label className="relative min-w-0 w-full">
          <span className="sr-only">{t("search")}</span>
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder={t("search")}
            className="h-9 w-full rounded border border-[#5A5A5A] bg-black px-3 pr-9 text-[14px] text-white outline-none placeholder:text-[#8A8A8A] focus:border-[#F4BB1B] [&::-webkit-search-cancel-button]:hidden [&::-webkit-search-decoration]:hidden"
          />
          {searchQuery ? (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 flex h-5 w-5 -translate-y-1/2 cursor-pointer items-center justify-center text-red-500 hover:text-red-400"
              aria-label={t("close")}
            >
              <X size={15} strokeWidth={2.5} />
            </button>
          ) : (
            <Search
              size={15}
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-white/70"
            />
          )}
        </label>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden border border-[#5A5A5A]">
        {banner ? (
          <div className="border-b border-[#F4BB1B]/35 bg-[#F4BB1B]/10 px-4 py-2 text-[13px] text-[#F4BB1B]">
            {banner}
          </div>
        ) : null}

        {isMobile ? (
          <div className="min-h-0 flex-1 overflow-hidden">
            {mobileShowDetails ? childrenPanel : treePanel}
          </div>
        ) : (
          <div
            className={`min-h-0 flex-1 overflow-hidden ${
              isDesktop
                ? "grid grid-cols-[20rem_minmax(0,1fr)]"
                : "grid grid-cols-1"
            }`}
          >
            {isDesktop ? (
              <div className="relative min-h-0 overflow-hidden border-r border-[#5A5A5A]">
                {treePanel}
              </div>
            ) : null}
            <div className="relative min-h-0 overflow-hidden">
              {childrenPanel}
            </div>
          </div>
        )}
      </div>

      {isTablet && drawerOpen ? (
        <div className="fixed inset-0 z-40 flex">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            aria-label={t("close")}
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="relative z-10 flex h-full w-[min(360px,85vw)] flex-col overflow-hidden border-r border-[#5A5A5A] bg-black shadow-2xl">
            <div className="flex shrink-0 items-center justify-between border-b border-[#5A5A5A] px-4 py-3">
              <h2 className="font-normal text-[16px] leading-none tracking-normal text-[#F4BB1B]">
                {t("geo_panel_hierarchy")}
              </h2>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="flex h-8 w-8 cursor-pointer items-center justify-center rounded hover:bg-white/10"
                aria-label={t("close")}
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {treePanel}
            </div>
          </aside>
        </div>
      ) : null}

      {dialog.open ? (
        <GeoNodeDialog
          open
          mode={dialog.mode}
          title={dialog.title}
          contextFields={dialog.contextFields}
          nameLabel={dialog.nameLabel}
          codeLabel={dialog.codeLabel}
          initialName={dialog.initialName}
          initialCode={dialog.initialCode}
          onClose={() => setDialog({ open: false })}
          onSubmit={() => {
            /* Write APIs not available yet — dialog shows notice. */
          }}
        />
      ) : null}

      <GeoLevelDialog
        open={levelDialogOpen}
        parentLevelLabel={addLevelParentLabel}
        onClose={() => setLevelDialogOpen(false)}
        onSubmit={() => {
          /* Write APIs not available yet — dialog shows notice. */
        }}
      />
    </section>
  );
}
