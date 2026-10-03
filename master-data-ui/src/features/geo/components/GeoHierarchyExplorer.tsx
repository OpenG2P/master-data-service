"use client";

import ConfirmDialog from "@/components/ConfirmDialog";
import SearchInput from "@/components/SearchInput";
import { errorMessage, useCatalogueApi } from "@/features/catalogue/api";
import type {
  GetGeoLevelsResponse,
  GetGeoUnitsResponse,
  VersionRef,
} from "@/features/catalogue/types";
import GeoChildrenTable from "./GeoChildrenTable";
import GeoManageLevelsDialog from "./GeoManageLevelsDialog";
import GeoNodeDialog, {
  type GeoNodeDialogField,
} from "./GeoNodeDialog";
import GeoTreePanel from "./GeoTreePanel";
import AddButton from "@/components/AddButton";
import Button from "@/components/Button";
import { toast } from "react-toastify";
import {
  childrenCacheKey,
  getChildLevels,
  getLevelById,
  getLevelLabel,
  getRootLevels,
  getValueLabel,
  levelNodeKey,
  orderGeoLevelsByHierarchy,
  valueNodeKey,
} from "../utils";
import type {
  ChildrenCacheEntry,
  GeoBreadcrumbItem,
  GeoLevel,
  GeoLevelValue,
  GeoTreeNode,
} from "../types";
import { ArrowLeft, MapPin, Menu, Settings2, X } from "lucide-react";
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
      levelId: string;
      parentLevelValueId: string | null;
      levelValueId?: string;
      levelChoices?: { levelId: string; label: string }[];
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

const UNITS_PAGE_SIZE = 1000;
const UNITS_MAX_PAGES = 50;

interface GeoHierarchyExplorerProps {
  /** Geography version to browse (catalogue): a number, "latest" or "draft". */
  version?: VersionRef;
  /** Edits allowed: the open DRAFT is shown and the user has geo:edit. */
  editable?: boolean;
  /** Also list RETIRED units. */
  includeRetired?: boolean;
  /** Rendered inside the Geo Locations tabs: no page title, shorter height. */
  embedded?: boolean;
  /** Called after an edit to the draft (to refresh version metadata). */
  onChanged?: () => void;
}

/**
 * Tree + table browser of the geography hierarchy at a version. Reads through the catalogue
 * (`get_geo_levels` / `get_geo_units`); when the open draft is shown, add / edit / retire and the
 * level editor write into that draft (`upsert_draft_units`, `retire_draft_units`, `upsert_draft_levels`).
 * Remount (change `key`) to switch version.
 */
export default function GeoHierarchyExplorer({
  version = "latest",
  editable = false,
  includeRetired = false,
  embedded = false,
  onChanged,
}: GeoHierarchyExplorerProps = {}) {
  const t = useTranslations();
  const call = useCatalogueApi();
  const width = useViewportWidth();
  const isDesktop = width > 1200;
  const isTablet = width >= 768 && width <= 1200;
  const isMobile = width < 768;

  const [nodeForm, setNodeForm] = useState<{
    open: boolean;
    mode: "add" | "edit";
    node?: GeoTreeNode;
    levelId: string;
    parentLevelValueId: string | null;
    contextFields: GeoNodeDialogField[];
  }>({
    open: false,
    mode: "add",
    levelId: "",
    parentLevelValueId: null,
    contextFields: [],
  });

  const [isSavingNode, setIsSavingNode] = useState(false);
  const [isDeletingNode, setIsDeletingNode] = useState(false);

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
  const [deleteValueTarget, setDeleteValueTarget] =
    useState<GeoLevelValue | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [breadcrumbMoreOpen, setBreadcrumbMoreOpen] = useState(false);
  const [manageLevelsOpen, setManageLevelsOpen] = useState(false);

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
      _valueLevelId: string,
      levelList: GeoLevel[]
    ) => {
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
            hasChildren: getChildLevels(levelList, value.level_id).length > 0,
          };
        }
        nodesByKeyRef.current = next;
        return next;
      });
    },
    []
  );

  const fetchGeoLevelValues = useCallback(
    async (
      levelId: string,
      parentLevelValueId: string,
      signal: AbortSignal
    ): Promise<GeoLevelValue[]> => {
      const out: GeoLevelValue[] = [];
      for (let page = 1; page <= UNITS_MAX_PAGES; page += 1) {
        const { payload } = await call<GetGeoUnitsResponse>(
          "get_geo_units",
          {
            version,
            level: levelId,
            // "" = units without a parent (top level)
            parent_unit_id: parentLevelValueId,
            include_retired: includeRetired,
          },
          { current_page: page, page_size: UNITS_PAGE_SIZE },
          signal
        );
        for (const unit of payload.units) {
          out.push({
            level_value_id: unit.unit_id,
            level_id: unit.level_id,
            level_value_mnemonic: unit.name,
            parent_level_value_id: unit.parent_unit_id ?? null,
            status: unit.status,
            name_i18n: unit.name_i18n ?? null,
          });
        }
        if (out.length >= payload.total || payload.units.length < UNITS_PAGE_SIZE) break;
      }
      return out;
    },
    [call, version, includeRetired]
  );

  const refreshLevels = useCallback(async (): Promise<GeoLevel[]> => {
    const { payload } = await call<GetGeoLevelsResponse>("get_geo_levels", { version });
    return payload.levels.map((level) => ({
      level_id: level.level_id,
      level_mnemonic: level.level_mnemonic,
      parent_level_id: level.parent_level_id ?? null,
      display: level.display ?? null,
      display_i18n: level.display_i18n ?? null,
    }));
  }, [call, version]);

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
          const values = await fetchGeoLevelValues(
            levelId,
            parentLevelValueId,
            controller.signal
          );
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
    [fetchGeoLevelValues, t]
  );

  const getFetchTargetsForNode = useCallback(
    (
      node: GeoTreeNode,
      levelList: GeoLevel[] = levelsRef.current
    ): { levelId: string; parentValueId: string }[] => {
      if (node.kind === "level") {
        return [{ levelId: node.levelId, parentValueId: "" }];
      }
      if (!node.value) return [];
      return getChildLevels(levelList, node.levelId).map((childLevel) => ({
        levelId: childLevel.level_id,
        parentValueId: node.value!.level_value_id,
      }));
    },
    []
  );

  const getCacheKeysForNode = useCallback(
    (node: GeoTreeNode) =>
      getFetchTargetsForNode(node).map((target) =>
        childrenCacheKey(target.levelId, target.parentValueId)
      ),
    [getFetchTargetsForNode]
  );

  const loadNodeChildren = useCallback(
    async (node: GeoTreeNode, force = false) => {
      const levelList = levelsRef.current;
      const targets = getFetchTargetsForNode(node, levelList);
      if (targets.length === 0) return;
      const entries = await Promise.all(
        targets.map((target) =>
          ensureChildren(target.levelId, target.parentValueId, force)
        )
      );
      const values = entries.flatMap((entry) => entry?.values ?? []);
      const loaded = entries.every((entry) => entry?.loaded);
      if (loaded) {
        materializeChildren(node, values, node.levelId, levelList);
      }
    },
    [ensureChildren, getFetchTargetsForNode, materializeChildren]
  );

  const loadLevels = useCallback(async () => {
    levelsAbortRef.current?.abort();
    const controller = new AbortController();
    levelsAbortRef.current = controller;

    setLevelsLoading(true);
    setLevelsError(null);
    setBanner(null);

    try {
      const data = await refreshLevels();
      const ordered = orderGeoLevelsByHierarchy(
        Array.isArray(data) ? data : []
      );
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
      setLevelsError(
        error instanceof Error ? error.message : t("geo_load_error")
      );
    } finally {
      setLevelsLoading(false);
    }
  }, [ensureChildren, materializeChildren, refreshLevels, t]);

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
    const cacheKeys = getCacheKeysForNode(selected);
    if (cacheKeys.length === 0) {
      return {
        values: [] as GeoLevelValue[],
        loading: false,
        error: null,
        loaded: true,
      };
    }
    const entries = cacheKeys.map((cacheKey) => childrenCache[cacheKey]);
    return {
      values: entries.flatMap((entry) => entry?.values ?? []),
      loading: cacheKeys.some(
        (cacheKey) =>
          !childrenCache[cacheKey] || childrenCache[cacheKey].loading
      ),
      error: entries.find((entry) => entry?.error)?.error ?? null,
      loaded: entries.every((entry) => entry?.loaded),
    };
  }, [childrenCache, getCacheKeysForNode, selected]);

  // Prefetch each row's child list so table/tree counts populate without expanding.
  useEffect(() => {
    if (!selectedChildrenEntry?.loaded) return;
    for (const value of selectedChildrenEntry.values) {
      for (const childLevel of getChildLevels(orderedLevels, value.level_id)) {
        void ensureChildren(childLevel.level_id, value.level_value_id);
      }
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
        hasChildren: getChildLevels(levelsRef.current, value.level_id).length > 0,
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
      const childLevels = getChildLevels(orderedLevels, value.level_id);
      if (childLevels.length === 0) return 0;
      let total = 0;
      for (const childLevel of childLevels) {
        const entry =
          childrenCache[
            childrenCacheKey(childLevel.level_id, value.level_value_id)
          ];
        if (!entry?.loaded) return null;
        total += entry.values.length;
      }
      return total;
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
        setNodeForm({
          open: true,
          mode: "add",
          levelId: level.level_id,
          parentLevelValueId: null,
          contextFields: [],
        });
        return;
      }

      const childLevels = getChildLevels(orderedLevels, parentNode.levelId);
      if (childLevels.length === 0 || !parentNode.value) return;
      const primary = childLevels[0];

      setNodeForm({
        open: true,
        mode: "add",
        levelId: parentNode.levelId,
        parentLevelValueId: parentNode.value.level_value_id,
        contextFields: parentNode.path.map((item) => ({
          label:
            item.kind === "level"
              ? t("geo_level")
              : getLevelLabel(getLevelById(orderedLevels, item.levelId)),
          value: item.label,
          readOnly: true,
        })),
      });
    },
    [orderedLevels, t]
  );

  const openEditDialog = useCallback(
    (node: GeoTreeNode) => {
      if (node.kind !== "value" || !node.value) return;
      const level = getLevelById(orderedLevels, node.levelId);
      setNodeForm({
        open: true,
        mode: "edit",
        node,
        levelId: node.value.level_id,
        parentLevelValueId: node.value.parent_level_value_id ?? null,
        contextFields: node.path.slice(0, -1).map((item) => ({
          label:
            item.kind === "level"
              ? t("geo_level")
              : getLevelLabel(getLevelById(orderedLevels, item.levelId)),
          value: item.label,
          readOnly: true,
        })),
      });
    },
    [orderedLevels, t]
  );

  const refreshSelectedChildren = useCallback(async () => {
    if (!selected) return;
    await loadNodeChildren(selected, true);
  }, [loadNodeChildren, selected]);

  const proceedDeleteValue = useCallback(
    async (value: GeoLevelValue) => {
      setIsDeletingNode(true);
      try {
        const { payload } = await call<{ retired: string[]; removed: string[] }>(
          "retire_draft_units",
          { unit_ids: [value.level_value_id], cascade: true }
        );
        toast.success(
          t("cat_units_retired", {
            retired: payload.retired.length,
            removed: payload.removed.length,
          })
        );
        setDeleteValueTarget(null);
        onChanged?.();
        await refreshSelectedChildren();
      } catch (error) {
        toast.error(errorMessage(error));
      } finally {
        setIsDeletingNode(false);
      }
    },
    [call, onChanged, refreshSelectedChildren, t]
  );

  const treePanel = (
    <div className="absolute inset-0 flex min-h-0 flex-col">
      <div className="shrink-0 border-b border-gray-200 px-4 py-2.5 text-start font-normal text-[16px] leading-none tracking-normal text-black">
        {t("geo_panel_hierarchy")}
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <GeoTreePanel
          nodes={nodes}
          expandedKeys={expandedKeys}
          selectedKey={selectedKey}
          childrenCache={childrenCache}
          getCacheKeysForNode={getCacheKeysForNode}
          searchQuery={searchQuery}
          onToggle={handleToggle}
          onSelect={handleSelect}
        />
      </div>
    </div>
  );

  const childrenPanelTitle = useMemo(() => {
    if (!selected) return t("geo_children");
    if (selected.kind === "level") {
      return t("geo_values_of_level", { name: selected.label });
    }
    return t("geo_children_of", { name: selected.label });
  }, [selected, t]);

  const childrenPanelSubtitle = useMemo(() => {
    if (!selected || selected.kind !== "value") return null;
    const childLevels = getChildLevels(orderedLevels, selected.levelId);
    if (childLevels.length === 0) {
      return t("geo_no_child_levels");
    }
    return childLevels.map((level) => getLevelLabel(level)).join(" · ");
  }, [orderedLevels, selected, t]);

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
    const childLevels = getChildLevels(orderedLevels, selected.levelId);
    if (childLevels.length === 0) return null;
    return {
      onClick: () => openAddDialog(selected),
    };
  }, [openAddDialog, orderedLevels, selected]);

  const childrenPanel = (
    <GeoChildrenTable
      selected={selected}
      title={childrenPanelTitle}
      subtitle={childrenPanelSubtitle}
      childrenEntry={selectedChildrenEntry}
      onSelect={handleSelectChild}
      onEdit={(value) => {
        if (!selected) return;
        const node =
          nodesByKeyRef.current[valueNodeKey(value.level_value_id)] ??
          buildChildNode(selected, value);
        openEditDialog(node);
      }}
      onDelete={(value) => setDeleteValueTarget(value)}
      readOnly={!editable}
      getChildCount={getChildCount}
      getLevelLabel={(value) =>
        getLevelLabel(getLevelById(orderedLevels, value.level_id))
      }
      deletingValueId={null}
      footerActions={
        addValueAction && editable ? (
          <AddButton onClick={addValueAction.onClick} label={t("geo_add_level_value")} />
        ) : null
      }
    />
  );


  if (levelsError) {
    return (
      <section className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 bg-white px-6 text-center text-black">
        <p className="text-[15px] text-red-500">{levelsError}</p>
        <Button onClick={() => void loadLevels()}>
          {t("refresh")}
        </Button>
      </section>
    );
  }

  return (
    <div
      className={`flex min-h-0 flex-col ${
        embedded ? "h-[max(32rem,calc(100dvh-20rem))]" : "h-[calc(100dvh-4rem)]"
      }`}
    >
      <div className={`flex shrink-0 items-center justify-between gap-4 ${embedded ? "mb-3" : "mb-6"}`}>
        {embedded ? (
          <span />
        ) : (
          <h1 className="font-semibold text-[24px] text-black">{t("geo_locations")}</h1>
        )}
        <div className="flex items-center gap-3">
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder={t("search")}
            width="w-[min(100%,20rem)] sm:w-80"
          />
          <Button
            variant="warning"
            onClick={() => setManageLevelsOpen(true)}
            className="inline-flex h-9 shrink-0 items-center gap-2"
          >
            <Settings2 size={15} />
            {editable ? t("geo_manage_levels") : t("cat_view_levels")}
          </Button>
        </div>
      </div>

      <section className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden bg-white p-3 text-black sm:gap-4 sm:p-5 rounded-[10px] shadow-sm">
      <div className="grid shrink-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <nav
          aria-label={t("geo_breadcrumb")}
          className="flex min-w-0 items-center gap-x-2 overflow-hidden font-normal text-[16px] leading-none tracking-normal"
        >
          {isMobile && mobileShowDetails ? (
            <button
              type="button"
              onClick={() => setMobileShowDetails(false)}
              className="mr-1 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded hover:bg-gray-100"
              aria-label={t("back")}
            >
              <ArrowLeft size={16} />
            </button>
          ) : null}
          {isTablet ? (
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="mr-1 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded border border-gray-300 hover:bg-gray-100"
              aria-label={t("geo_panel_hierarchy")}
            >
              <Menu size={16} />
            </button>
          ) : null}
          <button
            type="button"
            onClick={handleRootBreadcrumb}
            className={`inline-flex shrink-0 items-center gap-2 cursor-pointer hover:text-(--color-yellow) hover:underline ${
              selected ? "font-normal text-gray-600" : "text-black"
            }`}
          >
            <MapPin size={16} className="shrink-0 text-(--color-yellow)" />
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
                  <span className="text-black" aria-hidden>
                    &gt;
                  </span>
                  <button
                    type="button"
                    aria-expanded={breadcrumbMoreOpen}
                    aria-label={t("geo_breadcrumb_more")}
                    onClick={() => setBreadcrumbMoreOpen((open) => !open)}
                    className="cursor-pointer rounded px-1.5 font-normal text-gray-600 hover:bg-gray-100 hover:text-(--color-yellow)"
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
                      <ul className="absolute left-0 top-full z-30 mt-1 min-w-48 max-w-[18rem] rounded border border-gray-300 bg-white py-1 shadow-lg">
                        {breadcrumbSegments.collapsed.map((item) => (
                          <li key={`${item.kind}-${item.id}`}>
                            <button
                              type="button"
                              title={item.label}
                              onClick={() => {
                                setBreadcrumbMoreOpen(false);
                                handleBreadcrumbClick(item);
                              }}
                              className="block w-full cursor-pointer truncate px-3 py-1.5 text-left text-[14px] font-medium text-gray-700 hover:bg-gray-100 hover:text-(--color-yellow)"
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
                <span className="shrink-0 text-black" aria-hidden>
                  &gt;
                </span>
                {isLast ? (
                  <span className="min-w-0 truncate text-black" title={item.label}>
                    {item.label}
                  </span>
                ) : (
                  <button
                    type="button"
                    title={item.label}
                    onClick={() => handleBreadcrumbClick(item)}
                    className="min-w-0 max-w-36 cursor-pointer truncate font-normal text-gray-600 hover:text-(--color-yellow) hover:underline"
                  >
                    {item.label}
                  </button>
                )}
              </span>
            );
          })}
        </nav>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden border border-gray-200">
        {banner ? (
          <div className="border-b border-(--color-yellow)/35 bg-(--color-yellow)/10 px-4 py-2 text-[13px] text-(--color-yellow)">
            {banner}
          </div>
        ) : null}

        {isMobile ? (
          <div className="relative min-h-0 flex-1 overflow-hidden">
            {mobileShowDetails ? childrenPanel : treePanel}
          </div>
        ) : (
          <div
            className={`h-full min-h-0 flex-1 overflow-hidden ${
              isDesktop
                ? "grid grid-cols-[20rem_minmax(0,1fr)] grid-rows-[minmax(0,1fr)]"
                : "grid grid-cols-1 grid-rows-[minmax(0,1fr)]"
            }`}
          >
            {isDesktop ? (
              <div className="relative min-h-0 overflow-hidden border-r border-gray-200">
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
          <aside className="relative z-10 flex h-full w-[min(360px,85vw)] flex-col overflow-hidden border-r border-gray-200 bg-white shadow-2xl">
            <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-4 py-3">
              <h2 className="font-normal text-[16px] leading-none tracking-normal text-black">
                {t("geo_panel_hierarchy")}
              </h2>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="flex h-8 w-8 cursor-pointer items-center justify-center rounded hover:bg-gray-100"
                aria-label={t("close")}
              >
                <X size={16} />
              </button>
            </div>
            <div className="relative min-h-0 flex-1 overflow-hidden">
              {treePanel}
            </div>
          </aside>
        </div>
      ) : null}

      {nodeForm.open ? (
        <GeoNodeDialog
          open={nodeForm.open}
          mode={nodeForm.mode}
          title={nodeForm.mode === "add" ? t("geo_add_level_value") : t("geo_edit_level_value")}
          nameLabel={t("geo_level_value_mnemonic")}
          levelId={nodeForm.levelId}
          parentLevelValueId={nodeForm.parentLevelValueId}
          levelValueId={nodeForm.node?.kind === "value" ? nodeForm.node.value?.level_value_id : undefined}
          initialName={nodeForm.node?.kind === "value" ? nodeForm.node.label : ""}
          initialNameI18n={nodeForm.node?.kind === "value" ? nodeForm.node.value?.name_i18n : null}
          levelChoices={
            nodeForm.mode === "add" && nodeForm.parentLevelValueId
              ? getChildLevels(orderedLevels, nodeForm.levelId).map((l) => ({
                  levelId: l.level_id,
                  label: getLevelLabel(l),
                }))
              : []
          }
          contextFields={nodeForm.contextFields}
          onClose={() => {
            setNodeForm({ open: false, mode: "add", levelId: "", parentLevelValueId: null, contextFields: [] });
          }}
          onSuccess={async () => {
            onChanged?.();
            await refreshSelectedChildren();
            setNodeForm({ open: false, mode: "add", levelId: "", parentLevelValueId: null, contextFields: [] });
          }}
        />
      ) : null}

      <ConfirmDialog
        open={Boolean(deleteValueTarget)}
        title={t("cat_retire_unit_title")}
        message={t("cat_retire_unit_message", {
          name: deleteValueTarget ? getValueLabel(deleteValueTarget) : "",
        })}
        confirmLabel={t("cat_retire")}
        confirmingLabel={t("cat_retiring")}
        danger
        confirming={isDeletingNode}
        onConfirm={() => {
          if (!deleteValueTarget) return;
          void proceedDeleteValue(deleteValueTarget);
        }}
        onClose={() => setDeleteValueTarget(null)}
      />

      <GeoManageLevelsDialog
        open={manageLevelsOpen}
        levels={orderedLevels}
        readOnly={!editable}
        onClose={() => setManageLevelsOpen(false)}
        onChanged={async () => {
          onChanged?.();
          await loadLevels();
        }}
      />
    </section>
  </div>
  );
}
