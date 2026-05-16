"use client";

import { forceCollide, forceRadial } from "d3-force-3d";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import {
  fetchGraphQuery,
  type GraphQueryEdgeRead,
  type GraphQueryNodeRead,
  type GraphQueryRead,
} from "@/lib/api";
import type { ForceGraphMethods } from "react-force-graph-2d";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d").then((m) => m.default), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[280px] items-center justify-center font-mono text-xs text-muted">
      Loading graph…
    </div>
  ),
});

const DENSE_EDGE_THRESHOLD = 300;
const VERY_DENSE_EDGE_THRESHOLD = 500;
/** Extra floor for ``content_similarity`` only (structural edges use slider ``minWeight`` alone). */
const CONTENT_SIMILARITY_FLOOR_MODERATE = 0.28;
const CONTENT_SIMILARITY_FLOOR_HEAVY = 0.35;
const RELATED_CAP_OPTIONS = [10, 20, 40] as const;
const EDGES_PER_NODE_OPTIONS = [2, 3, 5, 10] as const;

type RelatedCapChoice = (typeof RELATED_CAP_OPTIONS)[number] | "all";
type EdgesPerNodeChoice = (typeof EDGES_PER_NODE_OPTIONS)[number] | "all";

type Selection =
  | { kind: "node"; node: GraphQueryNodeRead }
  | { kind: "edge"; edge: GraphQueryEdgeRead }
  | null;

type Props = {
  open: boolean;
  onClose: () => void;
  q: string;
  jobId: number | null;
};

function formatEvidence(evidence: unknown | null): string {
  if (evidence == null) return "—";
  if (typeof evidence === "string") return evidence;
  try {
    return JSON.stringify(evidence, null, 2);
  } catch {
    return String(evidence);
  }
}

function fallbackGraphEdgeReason(edgeType: string, weight: number): string {
  const et = edgeType.trim() || "unknown";
  const w = Number.isFinite(weight) ? weight : Number.NaN;
  const strength = Number.isFinite(w) ? String(w) : "unknown";
  return `Related by ${et} with strength ${strength}.`;
}

function displayEdgeReason(edge: GraphQueryEdgeRead): string {
  const r = edge.reason?.trim();
  if (r) return r;
  return fallbackGraphEdgeReason(edge.edge_type, edge.weight);
}

/** Lower = preferred when pruning / sorting. */
function edgeTypeRank(edgeType: string): number {
  switch (edgeType) {
    case "link":
      return 0;
    case "url_hierarchy":
      return 1;
    case "content_similarity":
      return 2;
    case "near_duplicate":
      return 3;
    default:
      return 4;
  }
}

function tooltipForEdgeType(edgeType: string): string {
  switch (edgeType) {
    case "link":
      return "Crawled hyperlinks between pages. Strong structural signal for how the site is wired.";
    case "url_hierarchy":
      return "URL path parent/child relationships (site folder structure), not page copy.";
    case "content_similarity":
      return "Similarity of page text/content. On very dense graphs the API may raise a minimum weight for this type only; the slider still applies to every edge type.";
    case "near_duplicate":
      return "Pairs flagged as near-duplicates in the crawl graph.";
    case "same_domain":
    case "same_site":
      return "Same host or site grouping used when building the graph.";
    case "outbound_link":
      return "Outbound links recorded on a page.";
    default:
      return `Toggle whether ${edgeType.replace(/_/g, " ")} edges appear in the map and in edge counts.`;
  }
}

function edgeColorForType(edgeType: string, alpha: number): string {
  switch (edgeType) {
    case "link":
      return `rgba(90, 110, 200, ${alpha})`;
    case "url_hierarchy":
      return `rgba(60, 130, 100, ${alpha})`;
    case "content_similarity":
      return `rgba(140, 90, 160, ${alpha})`;
    case "near_duplicate":
      return `rgba(180, 120, 40, ${alpha})`;
    case "same_domain":
    case "same_site":
      return `rgba(60, 130, 100, ${alpha})`;
    case "outbound_link":
      return `rgba(90, 110, 200, ${alpha})`;
    default:
      return `rgba(120, 118, 110, ${alpha})`;
  }
}

function edgeDashForType(edgeType: string): number[] | null {
  if (edgeType === "near_duplicate") return [5, 4];
  return null;
}

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function nodeDisplayTitle(n: GraphQueryNodeRead): string {
  const t = n.title?.trim();
  if (t) return t;
  return safeHostname(n.url);
}

function requestElementFullscreen(el: HTMLElement): Promise<void> | void {
  const wk = el as HTMLElement & { webkitRequestFullscreen?: () => void };
  return el.requestFullscreen?.() ?? wk.webkitRequestFullscreen?.();
}

function exitDocumentFullscreen(): Promise<void> | void {
  const doc = document as Document & { webkitExitFullscreen?: () => void };
  return document.exitFullscreen?.() ?? doc.webkitExitFullscreen?.();
}

function getFullscreenElement(): Element | null {
  const doc = document as Document & { webkitFullscreenElement?: Element | null };
  return document.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
}

function IconFullscreenEnter({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7M3 9V3h6M21 15v6h-6" />
    </svg>
  );
}

function IconFullscreenExit({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 8V4h4M20 16v4h-4M16 4h4v4M8 20H4v-4" />
    </svg>
  );
}

function truncateCanvasLabel(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
  if (!text) return "";
  if (ctx.measureText(text).width <= maxWidth) return text;
  const ell = "…";
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    const sub = text.slice(0, mid) + ell;
    if (ctx.measureText(sub).width <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return text.slice(0, lo) + ell;
}

function sortPagesForList<T extends GraphQueryNodeRead>(nodes: T[]): T[] {
  const roleRank: Record<string, number> = { query_match: 0, related_neighbor: 1, duplicate: 2 };
  return [...nodes].sort((a, b) => {
    const ra = roleRank[a.role] ?? 9;
    const rb = roleRank[b.role] ?? 9;
    if (ra !== rb) return ra - rb;
    const ba = a.bm25_score ?? -1;
    const bb = b.bm25_score ?? -1;
    return bb - ba;
  });
}

function normalizeLinkEndpoints(link: {
  edge_id: number;
  source_page_id: number;
  target_page_id: number;
  edge_type: string;
  weight: number;
  evidence: unknown | null;
  source?: unknown;
  target?: unknown;
}): { source_page_id: number; target_page_id: number } {
  let s = link.source_page_id;
  let t = link.target_page_id;
  if (typeof link.source === "object" && link.source !== null && "page_id" in (link.source as { page_id: number })) {
    s = (link.source as { page_id: number }).page_id;
  } else if (typeof link.source === "number") s = link.source;
  if (typeof link.target === "object" && link.target !== null && "page_id" in (link.target as { page_id: number })) {
    t = (link.target as { page_id: number }).page_id;
  } else if (typeof link.target === "number") t = link.target;
  return { source_page_id: s, target_page_id: t };
}

function pagerankOrNegInf(n: GraphQueryNodeRead): number {
  const p = n.metrics?.pagerank;
  if (p == null || !Number.isFinite(p)) return Number.NEGATIVE_INFINITY;
  return p;
}

function linkEndpointId(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (v && typeof v === "object" && "page_id" in (v as object)) {
    return (v as { page_id: number }).page_id;
  }
  return Number(v);
}

function contentSimilarityWeightFloor(apiEdgeCount: number): number {
  if (apiEdgeCount > VERY_DENSE_EDGE_THRESHOLD) return CONTENT_SIMILARITY_FLOOR_HEAVY;
  if (apiEdgeCount > DENSE_EDGE_THRESHOLD) return CONTENT_SIMILARITY_FLOOR_MODERATE;
  return 0;
}

function buildMaxWeightToQueryMatches(
  queryMatchIds: Set<number>,
  baseIds: Set<number>,
  edges: GraphQueryEdgeRead[],
  edgeTypeOn: Record<string, boolean>,
  minWeightUser: number,
  apiEdgeCount: number,
): Map<number, number> {
  const simFloor = contentSimilarityWeightFloor(apiEdgeCount);
  const m = new Map<number, number>();
  for (const e of edges) {
    if (!edgeTypeOn[e.edge_type]) continue;
    let wMin = minWeightUser;
    if (e.edge_type === "content_similarity") {
      wMin = Math.max(wMin, simFloor);
    }
    if (e.weight < wMin) continue;
    const a = e.source_page_id;
    const b = e.target_page_id;
    if (!baseIds.has(a) || !baseIds.has(b)) continue;
    let rn: number | null = null;
    if (queryMatchIds.has(a) && !queryMatchIds.has(b)) rn = b;
    else if (queryMatchIds.has(b) && !queryMatchIds.has(a)) rn = a;
    if (rn == null) continue;
    const prev = m.get(rn) ?? 0;
    if (e.weight > prev) m.set(rn, e.weight);
  }
  return m;
}

function sortRelatedNeighbors(
  neighbors: GraphQueryNodeRead[],
  maxWeightToQm: Map<number, number>,
): GraphQueryNodeRead[] {
  return [...neighbors].sort((a, b) => {
    const da = a.depth;
    const db = b.depth;
    if (da !== db) return da - db;
    const wa = maxWeightToQm.get(a.page_id) ?? 0;
    const wb = maxWeightToQm.get(b.page_id) ?? 0;
    if (wa !== wb) return wb - wa;
    const pa = pagerankOrNegInf(a);
    const pb = pagerankOrNegInf(b);
    if (pa !== pb) return pb - pa;
    return a.page_id - b.page_id;
  });
}

function pruneEdgesForMiniMap(
  visibleNodes: GraphQueryNodeRead[],
  edges: (GraphQueryEdgeRead & { source: number; target: number })[],
  qmIds: Set<number>,
  kPerNode: number,
): { pruned: (GraphQueryEdgeRead & { source: number; target: number })[]; beforeCount: number } {
  const beforeCount = edges.length;
  const idSet = new Set(visibleNodes.map((n) => n.page_id));
  const roleById = new Map(visibleNodes.map((n) => [n.page_id, n.role]));

  const eligible = edges.filter((e) => idSet.has(e.source) && idSet.has(e.target));
  const isQmRnBridge = (e: (typeof eligible)[0]) => {
    const ra = roleById.get(e.source);
    const rb = roleById.get(e.target);
    return (
      (ra === "query_match" && rb === "related_neighbor") || (rb === "query_match" && ra === "related_neighbor")
    );
  };

  const key = (e: (typeof eligible)[0]) => `${e.source}|${e.target}|${e.edge_type}|${e.edge_id}`;

  const qmRn = eligible.filter(isQmRnBridge);
  const rawForcedStructural = qmRn.filter((e) => e.edge_type === "link" || e.edge_type === "url_hierarchy");
  const rawForcedSimNd = qmRn.filter(
    (e) => e.edge_type === "content_similarity" || e.edge_type === "near_duplicate",
  );

  const groupByRelated = (
    list: (typeof eligible)[0][],
  ): Map<number, (typeof eligible)[0][]> => {
    const m = new Map<number, (typeof eligible)[0][]>();
    for (const e of list) {
      const relatedId = qmIds.has(e.source) ? e.target : e.source;
      const arr = m.get(relatedId) ?? [];
      arr.push(e);
      m.set(relatedId, arr);
    }
    return m;
  };

  const structByRelated = groupByRelated(rawForcedStructural);
  const forcedStructuralCapped: (typeof eligible)[0][] = [];
  for (const arr of Array.from(structByRelated.values())) {
    arr.sort(
      (a: (typeof eligible)[0], b: (typeof eligible)[0]) =>
        edgeTypeRank(a.edge_type) - edgeTypeRank(b.edge_type) ||
        b.weight - a.weight ||
        a.edge_id - b.edge_id,
    );
    forcedStructuralCapped.push(...arr.slice(0, 2));
  }

  const simByRelated = groupByRelated(rawForcedSimNd);
  const forcedSimCapped: (typeof eligible)[0][] = [];
  for (const arr of Array.from(simByRelated.values())) {
    arr.sort((a: (typeof eligible)[0], b: (typeof eligible)[0]) => b.weight - a.weight || a.edge_id - b.edge_id);
    forcedSimCapped.push(...arr.slice(0, 1));
  }

  const forced = [...forcedStructuralCapped, ...forcedSimCapped];
  const forcedKeys = new Set(forced.map(key));
  const pool = eligible.filter((e) => !forcedKeys.has(key(e)));

  pool.sort((a, b) => {
    const ta = edgeTypeRank(a.edge_type);
    const tb = edgeTypeRank(b.edge_type);
    if (ta !== tb) return ta - tb;
    if (b.weight !== a.weight) return b.weight - a.weight;
    return a.edge_id - b.edge_id;
  });

  const degree = new Map<number, number>();
  const addEdge = (e: (typeof eligible)[0]) => {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  };

  const out: (typeof eligible)[0][] = [];
  const seen = new Set<string>();

  for (const e of forced) {
    const k = key(e);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(e);
    addEdge(e);
  }

  const cap = kPerNode >= 900 ? Number.POSITIVE_INFINITY : kPerNode;

  for (const e of pool) {
    const k = key(e);
    if (seen.has(k)) continue;
    if (Number.isFinite(cap)) {
      const ds = degree.get(e.source) ?? 0;
      const dt = degree.get(e.target) ?? 0;
      if (ds >= cap || dt >= cap) continue;
    }
    seen.add(k);
    out.push(e);
    addEdge(e);
  }

  return { pruned: out, beforeCount };
}

export function RelationshipMapModal({ open, onClose, q, jobId }: Props) {
  const [raw, setRaw] = useState<GraphQueryRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [hideDuplicateNodes, setHideDuplicateNodes] = useState(true);
  const [minWeight, setMinWeight] = useState(0);
  const [edgeTypeOn, setEdgeTypeOn] = useState<Record<string, boolean>>({});
  const [relatedCap, setRelatedCap] = useState<RelatedCapChoice>(10);
  const [edgesPerNode, setEdgesPerNode] = useState<EdgesPerNodeChoice>(2);
  const [hoverId, setHoverId] = useState<number | null>(null);
  const [hoverLinkId, setHoverLinkId] = useState<number | null>(null);
  const [graphBg, setGraphBg] = useState("rgb(244, 241, 234)");
  const [isDark, setIsDark] = useState(false);
  const [accentRgb, setAccentRgb] = useState("107, 75, 62");
  const [mutedRgb, setMutedRgb] = useState("92, 90, 86");
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  const [dims, setDims] = useState({ w: 520, h: 320 });
  const [layoutKey, setLayoutKey] = useState(0);
  const [graphIsFullscreen, setGraphIsFullscreen] = useState(false);
  /** Radial seed + force tuning use this, updated only when graph membership changes — not on fullscreen resize. */
  const [seedLayoutMinDim, setSeedLayoutMinDim] = useState(320);
  const lastGraphSeedMemberKeyRef = useRef("");
  /** Saved zoom/pan before entering graph fullscreen — reapplied after exit so the view matches pre-fullscreen. */
  const cameraBeforeFsRef = useRef<{ k: number; cx: number; cy: number } | null>(null);
  const pendingGraphCameraRestoreRef = useRef(false);

  useEffect(() => {
    const el = document.documentElement;
    const syncPaper = () => {
      const dark = el.classList.contains("dark");
      setIsDark(dark);
      setGraphBg(dark ? "rgb(17, 16, 15)" : "rgb(244, 241, 234)");
      const cs = getComputedStyle(el);
      const accent = cs.getPropertyValue("--accent-rgb").trim();
      const muted = cs.getPropertyValue("--muted-rgb").trim();
      if (accent) setAccentRgb(accent.replace(/\s+/g, ", "));
      if (muted) setMutedRgb(muted.replace(/\s+/g, ", "));
    };
    syncPaper();
    const mo = new MutationObserver(syncPaper);
    mo.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    if (!open && getFullscreenElement()) {
      void Promise.resolve(exitDocumentFullscreen()).catch(() => {});
    }
  }, [open]);

  useEffect(() => {
    const sync = () => {
      const wrap = wrapRef.current;
      const nowFs = wrap != null && getFullscreenElement() === wrap;
      setGraphIsFullscreen(nowFs);
      if (!nowFs && cameraBeforeFsRef.current != null) {
        pendingGraphCameraRestoreRef.current = true;
      }
    };
    document.addEventListener("fullscreenchange", sync);
    document.addEventListener("webkitfullscreenchange", sync as EventListener);
    sync();
    return () => {
      document.removeEventListener("fullscreenchange", sync);
      document.removeEventListener("webkitfullscreenchange", sync as EventListener);
    };
  }, []);

  useEffect(() => {
    if (open) return;
    cameraBeforeFsRef.current = null;
    pendingGraphCameraRestoreRef.current = false;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setDims({
        w: Math.max(200, Math.floor(r.width)),
        h: Math.max(200, Math.floor(r.height)),
      });
    });
    ro.observe(el);
    const r = el.getBoundingClientRect();
    setDims({
      w: Math.max(200, Math.floor(r.width)),
      h: Math.max(200, Math.floor(r.height)),
    });
    return () => ro.disconnect();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const query = q.trim();
    if (!query) return;

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    setSelection(null);
    setRaw(null);
    setHideDuplicateNodes(true);
    setMinWeight(0);
    setRelatedCap(10);
    setEdgesPerNode(2);
    setHoverId(null);
    setHoverLinkId(null);

    fetchGraphQuery({
      q: query,
      job_id: jobId ?? undefined,
      max_seed_pages: 10,
      radius: 1,
      max_nodes: 50,
    })
      .then((res) => {
        if (cancelled) return;
        setRaw(res);
        const types = new Set(res.edges.map((e) => e.edge_type));
        const next: Record<string, boolean> = {};
        Array.from(types).forEach((t) => {
          next[t] = true;
        });
        setEdgeTypeOn(next);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setErrorMessage(err instanceof Error ? err.message : "Failed to load graph.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, q, jobId]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      const wrap = wrapRef.current;
      if (wrap && getFullscreenElement() === wrap) {
        void Promise.resolve(exitDocumentFullscreen()).catch(() => {});
        return;
      }
      onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const toggleGraphFullscreen = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    if (getFullscreenElement() === el) {
      void Promise.resolve(exitDocumentFullscreen()).catch(() => {});
      return;
    }
    const fg = fgRef.current;
    if (fg) {
      try {
        const at = fg.centerAt();
        cameraBeforeFsRef.current = { k: fg.zoom(), cx: at.x, cy: at.y };
      } catch {
        cameraBeforeFsRef.current = null;
      }
    } else {
      cameraBeforeFsRef.current = null;
    }
    void Promise.resolve(requestElementFullscreen(el)).catch(() => {
      cameraBeforeFsRef.current = null;
    });
  }, []);

  const baseNodes = useMemo(() => {
    if (!raw) return [] as GraphQueryNodeRead[];
    return raw.nodes.filter((n) => !(hideDuplicateNodes && n.role === "duplicate"));
  }, [raw, hideDuplicateNodes]);

  const baseIdSet = useMemo(() => new Set(baseNodes.map((n) => n.page_id)), [baseNodes]);

  const weightExtent = useMemo(() => {
    if (!raw?.edges.length) return { min: 0, max: 1 };
    let min = raw.edges[0].weight;
    let max = min;
    for (const e of raw.edges) {
      if (e.weight < min) min = e.weight;
      if (e.weight > max) max = e.weight;
    }
    if (max <= min) return { min, max: min + 1e-6 };
    return { min, max };
  }, [raw]);

  const effectiveMinForEdge = useCallback(
    (e: GraphQueryEdgeRead) => {
      const m = minWeight;
      const simFloor = contentSimilarityWeightFloor(raw?.edges.length ?? 0);
      if (e.edge_type === "content_similarity") {
        return Math.max(m, simFloor);
      }
      return m;
    },
    [minWeight, raw?.edges.length],
  );

  /** Edges after type toggles + weight floor (still full node set from API response). */
  const edgesAfterFilters = useMemo(() => {
    if (!raw) return [] as (GraphQueryEdgeRead & { source: number; target: number })[];
    const out: (GraphQueryEdgeRead & { source: number; target: number })[] = [];
    for (const e of raw.edges) {
      if (!edgeTypeOn[e.edge_type]) continue;
      if (e.weight < effectiveMinForEdge(e)) continue;
      if (!baseIdSet.has(e.source_page_id) || !baseIdSet.has(e.target_page_id)) continue;
      if (e.source_page_id === e.target_page_id) continue;
      out.push({
        ...e,
        source: e.source_page_id,
        target: e.target_page_id,
      });
    }
    return out;
  }, [raw, edgeTypeOn, effectiveMinForEdge, baseIdSet]);

  const queryMatches = useMemo(() => baseNodes.filter((n) => n.role === "query_match"), [baseNodes]);
  const relatedPool = useMemo(() => baseNodes.filter((n) => n.role === "related_neighbor"), [baseNodes]);
  const qmIdSet = useMemo(() => new Set(queryMatches.map((n) => n.page_id)), [queryMatches]);

  const maxWeightToQm = useMemo(() => {
    return buildMaxWeightToQueryMatches(
      qmIdSet,
      baseIdSet,
      raw?.edges ?? [],
      edgeTypeOn,
      minWeight,
      raw?.edges.length ?? 0,
    );
  }, [qmIdSet, baseIdSet, raw?.edges, edgeTypeOn, minWeight]);

  const sortedRelated = useMemo(
    () => sortRelatedNeighbors(relatedPool, maxWeightToQm),
    [relatedPool, maxWeightToQm],
  );

  const curatedNodes = useMemo(() => {
    const rnTake =
      relatedCap === "all" ? sortedRelated : sortedRelated.slice(0, Math.min(sortedRelated.length, relatedCap));
    const seen = new Set<number>();
    const out: GraphQueryNodeRead[] = [];
    for (const n of queryMatches) {
      if (seen.has(n.page_id)) continue;
      seen.add(n.page_id);
      out.push(n);
    }
    for (const n of rnTake) {
      if (seen.has(n.page_id)) continue;
      seen.add(n.page_id);
      out.push(n);
    }
    return out;
  }, [queryMatches, sortedRelated, relatedCap]);

  const visibleIdSet = useMemo(() => new Set(curatedNodes.map((n) => n.page_id)), [curatedNodes]);

  const edgesForVisibleInduced = useMemo(() => {
    return edgesAfterFilters.filter((e) => visibleIdSet.has(e.source) && visibleIdSet.has(e.target));
  }, [edgesAfterFilters, visibleIdSet]);

  const kEdges = edgesPerNode === "all" ? 999 : edgesPerNode;

  const { prunedLinks, edgeCountBeforePrune } = useMemo(() => {
    const { pruned, beforeCount } = pruneEdgesForMiniMap(curatedNodes, edgesForVisibleInduced, qmIdSet, kEdges);
    return { prunedLinks: pruned, edgeCountBeforePrune: beforeCount };
  }, [curatedNodes, edgesForVisibleInduced, qmIdSet, kEdges]);

  const graphMemberKey = useMemo(() => {
    if (!curatedNodes.length) return "";
    const p = curatedNodes.map((n) => n.page_id).join("-");
    const e = [...prunedLinks]
      .sort((a, b) => a.edge_id - b.edge_id)
      .map((l) => l.edge_id)
      .join("-");
    return `${layoutKey}|${p}|${e}`;
  }, [curatedNodes, prunedLinks, layoutKey]);

  useEffect(() => {
    if (!open) {
      lastGraphSeedMemberKeyRef.current = "";
      return;
    }
    if (!graphMemberKey) return;
    if (lastGraphSeedMemberKeyRef.current === graphMemberKey) return;
    lastGraphSeedMemberKeyRef.current = graphMemberKey;
    const el = wrapRef.current;
    const r = el?.getBoundingClientRect();
    const w = r && r.width >= 200 ? Math.floor(r.width) : dims.w;
    const h = r && r.height >= 200 ? Math.floor(r.height) : dims.h;
    setSeedLayoutMinDim(Math.max(200, Math.min(w, h)));
  }, [open, graphMemberKey, dims.w, dims.h]);

  const graphData = useMemo(() => {
    const nodes = curatedNodes.map((n) => ({
      ...n,
      id: n.page_id,
    })) as (GraphQueryNodeRead & { id: number; x?: number; y?: number })[];
    const qm = nodes.filter((n) => n.role === "query_match");
    const rn = nodes.filter((n) => n.role === "related_neighbor");
    const cx = 0;
    const cy = 0;
    const minDim = seedLayoutMinDim;
    const r1 = Math.max(60, minDim * 0.16);
    const r2 = Math.max(160, minDim * 0.46);
    const rot = layoutKey * 0.35;
    const stab = (seed: number) => (((seed * 9301 + 49297) % 233280) / 233280 - 0.5) * 24;
    qm.forEach((n, i) => {
      const ang = rot + (2 * Math.PI * i) / Math.max(qm.length, 1);
      n.x = cx + r1 * Math.cos(ang) + stab(n.page_id);
      n.y = cy + r1 * Math.sin(ang) + stab(n.page_id + 17);
    });
    rn.forEach((n, i) => {
      const ang = rot + (2 * Math.PI * i) / Math.max(rn.length, 1);
      n.x = cx + r2 * Math.cos(ang) + stab(n.page_id + 31);
      n.y = cy + r2 * Math.sin(ang) + stab(n.page_id + 53);
    });
    const rest = nodes.filter((n) => n.role !== "query_match" && n.role !== "related_neighbor");
    rest.forEach((n, i) => {
      const ang = rot + (2 * Math.PI * i) / Math.max(rest.length, 1);
      const r3 = r2 + minDim * 0.09;
      n.x = cx + r3 * Math.cos(ang) + stab(n.page_id + 91);
      n.y = cy + r3 * Math.sin(ang) + stab(n.page_id + 103);
    });
    return { nodes, links: prunedLinks };
  }, [curatedNodes, prunedLinks, layoutKey, seedLayoutMinDim]);

  const hoverLinkEndpoints = useMemo(() => {
    if (hoverLinkId == null) return null as Set<number> | null;
    const l = prunedLinks.find((e) => e.edge_id === hoverLinkId);
    if (!l) return null;
    return new Set([linkEndpointId(l.source), linkEndpointId(l.target)]);
  }, [hoverLinkId, prunedLinks]);

  const highlightSeeds = useMemo(() => {
    const seeds = new Set<number>();
    if (hoverId != null) seeds.add(hoverId);
    if (hoverLinkEndpoints) {
      for (const id of Array.from(hoverLinkEndpoints)) seeds.add(id);
    }
    if (selection?.kind === "node") seeds.add(selection.node.page_id);
    if (selection?.kind === "edge") {
      seeds.add(selection.edge.source_page_id);
      seeds.add(selection.edge.target_page_id);
    }
    return seeds;
  }, [hoverId, hoverLinkEndpoints, selection]);

  const highlightNodeSet = useMemo(() => {
    if (highlightSeeds.size === 0) return null as Set<number> | null;
    const out = new Set<number>(highlightSeeds);
    for (const l of prunedLinks) {
      const a = linkEndpointId(l.source);
      const b = linkEndpointId(l.target);
      if (highlightSeeds.has(a)) out.add(b);
      if (highlightSeeds.has(b)) out.add(a);
    }
    return out;
  }, [highlightSeeds, prunedLinks]);

  const graphHasFocus = highlightSeeds.size > 0;

  const visibleNodeCount = graphData.nodes.length;

  const selectedPageId = selection?.kind === "node" ? selection.node.page_id : null;

  const graphSummary = useMemo(() => {
    if (!raw) return null;
    const apiEdgeCount = raw.edges.length;
    const simFloor = contentSimilarityWeightFloor(apiEdgeCount);
    const drawnPct = apiEdgeCount > 0 ? (100 * prunedLinks.length) / apiEdgeCount : 0;
    return {
      query: raw.query,
      apiNodeCount: baseNodes.length,
      visibleNodeCount: curatedNodes.length,
      apiEdgeCount,
      edgeCountAfterFilters: edgesAfterFilters.length,
      edgeCountVisible: prunedLinks.length,
      edgeCountBeforePrune,
      queryMatches: curatedNodes.filter((n) => n.role === "query_match").length,
      relatedNeighbors: curatedNodes.filter((n) => n.role === "related_neighbor").length,
      duplicateNodes: raw.nodes.filter((n) => n.role === "duplicate").length,
      selectedJob: raw.selected_job,
      minWeightActive: minWeight,
      contentSimilarityFloor: simFloor,
      densePruningActive: apiEdgeCount > VERY_DENSE_EDGE_THRESHOLD,
      drawnEdgePct: drawnPct,
      edgesPerNodeCap: edgesPerNode,
      relatedNeighborCap: relatedCap,
    };
  }, [
    raw,
    baseNodes,
    curatedNodes,
    edgesAfterFilters.length,
    prunedLinks.length,
    edgeCountBeforePrune,
    minWeight,
    edgesPerNode,
    relatedCap,
  ]);

  const showNoApiEdgesBanner = Boolean(raw && raw.nodes.length > 0 && raw.edges.length === 0);
  const showFilteredEdgesBanner = Boolean(
    raw && raw.nodes.length > 0 && raw.edges.length > 0 && edgesAfterFilters.length === 0,
  );

  const sortedPagesList = useMemo(() => sortPagesForList(graphData.nodes), [graphData.nodes]);

  const shouldDrawNodeLabel = useCallback(
    (node: GraphQueryNodeRead) => {
      if (node.role === "query_match") return true;
      if (hoverId === node.page_id || selectedPageId === node.page_id) return true;
      if (hoverLinkEndpoints?.has(node.page_id)) return true;
      if (
        selection?.kind === "edge" &&
        (node.page_id === selection.edge.source_page_id || node.page_id === selection.edge.target_page_id)
      ) {
        return true;
      }
      return visibleNodeCount > 0 && visibleNodeCount <= 15;
    },
    [visibleNodeCount, hoverId, selectedPageId, hoverLinkEndpoints, selection],
  );

  const nodeCanvasObject = useCallback(
    (node: Record<string, unknown>, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as GraphQueryNodeRead & { id: number; x?: number; y?: number };
      if (n.x == null || n.y == null) return;

      const dim =
        graphHasFocus &&
        highlightNodeSet != null &&
        !highlightNodeSet.has(n.page_id);
      const rBase = n.role === "query_match" ? 9 : n.role === "related_neighbor" ? 5 : 4;
      const r = (rBase / globalScale) * (dim ? 0.85 : 1);

      if (selectedPageId === n.page_id) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 3 / globalScale, 0, 2 * Math.PI);
        ctx.strokeStyle = `rgba(${accentRgb}, 0.95)`;
        ctx.lineWidth = 2.5 / globalScale;
        ctx.stroke();
      }

      if (!shouldDrawNodeLabel(n)) return;

      const rawLabel = nodeDisplayTitle(n);
      const basePx = n.role === "query_match" ? 10 : 9;
      const fontPx = Math.max(7, basePx / globalScale);
      ctx.font = `${fontPx}px "IBM Plex Sans", system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";

      const maxW =
        n.role === "query_match"
          ? Math.min(48, 40 / Math.max(0.35, globalScale))
          : Math.min(88, 72 / Math.max(0.35, globalScale));
      const label = truncateCanvasLabel(ctx, rawLabel, maxW);
      const offsetY = 8 / globalScale + (n.role === "query_match" ? 5 : 3) / globalScale;

      const fill = dim ? (isDark ? "rgb(140, 138, 130)" : "rgb(100, 98, 92)") : isDark ? "rgb(232, 230, 225)" : "rgb(26, 25, 23)";
      ctx.lineJoin = "round";
      ctx.miterLimit = 2;
      ctx.lineWidth = 3 / globalScale;
      ctx.strokeStyle = graphBg;
      ctx.strokeText(label, n.x, n.y + offsetY);
      ctx.fillStyle = fill;
      ctx.fillText(label, n.x, n.y + offsetY);
    },
    [
      shouldDrawNodeLabel,
      isDark,
      graphBg,
      accentRgb,
      selectedPageId,
      graphHasFocus,
      highlightNodeSet,
    ],
  );

  const edgeTypes = useMemo(() => {
    if (!raw) return [];
    const u = new Set(raw.edges.map((e) => e.edge_type));
    return Array.from(u).sort();
  }, [raw]);

  const linkWidthScale = useCallback(
    (w: number) => {
      const { min, max } = weightExtent;
      const t = (w - min) / (max - min);
      return 0.45 + Math.max(0, Math.min(1, t)) * 3.2;
    },
    [weightExtent],
  );

  const applyRingInitialLayout = useCallback(() => {
    setLayoutKey((k) => k + 1);
    window.setTimeout(() => fgRef.current?.d3ReheatSimulation(), 0);
    window.setTimeout(() => fgRef.current?.zoomToFit(400, 56), 140);
  }, []);

  const onEngineStop = useCallback(() => {
    fgRef.current?.zoomToFit(500, 56);
  }, []);

  useEffect(() => {
    if (loading || !graphData.nodes.length) return;
    const fg = fgRef.current;
    if (!fg) return;
    const minDim = seedLayoutMinDim;
    const innerR = Math.max(60, minDim * 0.16);
    const outerR = Math.max(160, minDim * 0.46);

    const charge = fg.d3Force("charge") as unknown as { strength?: (n?: number) => unknown } | undefined;
    charge?.strength?.(-1100);
    const link = fg.d3Force("link") as unknown as
      | { distance?: (n?: number) => unknown; strength?: (n?: number) => unknown }
      | undefined;
    link?.distance?.(140);
    link?.strength?.(0.15);

    const collide = forceCollide()
      .radius((n: unknown) => {
        const nd = n as GraphQueryNodeRead & { id: number };
        return nd.role === "query_match" ? 32 : nd.role === "related_neighbor" ? 22 : 18;
      })
      .strength(1);
    fg.d3Force("collide", collide as never);

    const radial = forceRadial((n: unknown) => {
      const nd = n as GraphQueryNodeRead & { id: number };
      if (nd.role === "query_match") return innerR;
      if (nd.role === "related_neighbor") return outerR;
      return outerR + 40;
    }, 0, 0).strength((n: unknown) => {
      const nd = n as GraphQueryNodeRead & { id: number };
      if (nd.role === "query_match") return 0.45;
      if (nd.role === "related_neighbor") return 0.35;
      return 0.3;
    });
    fg.d3Force("radial", radial as never);
  }, [loading, graphData.nodes.length, graphData.links.length, seedLayoutMinDim]);

  useEffect(() => {
    if (loading || !open) return;
    if (!graphData.nodes.length) return;
    fgRef.current?.d3ReheatSimulation();
    const t = window.setTimeout(() => fgRef.current?.zoomToFit(500, 56), 220);
    return () => window.clearTimeout(t);
  }, [loading, open, graphData.nodes.length, graphData.links.length, layoutKey]);

  useEffect(() => {
    if (!pendingGraphCameraRestoreRef.current) return;
    const saved = cameraBeforeFsRef.current;
    if (!saved || loading || !graphData.nodes.length) return;
    if (typeof document !== "undefined" && document.fullscreenElement != null) return;

    let cancelled = false;
    const tid = window.setTimeout(() => {
      if (cancelled) return;
      const fg = fgRef.current;
      const wrap = wrapRef.current;
      const stillSaved = cameraBeforeFsRef.current;
      if (!fg || !wrap || !stillSaved || getFullscreenElement() === wrap) return;
      fg.zoom(stillSaved.k);
      fg.centerAt(stillSaved.cx, stillSaved.cy);
      cameraBeforeFsRef.current = null;
      pendingGraphCameraRestoreRef.current = false;
    }, 96);
    return () => {
      cancelled = true;
      window.clearTimeout(tid);
    };
  }, [dims.w, dims.h, loading, graphData.nodes.length]);

  if (!open) return null;

  const apiEmpty = raw && raw.nodes.length === 0;
  const filteredEmpty = raw && raw.nodes.length > 0 && curatedNodes.length === 0;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-end justify-center bg-black/45 p-3 sm:items-center sm:p-6"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="relationship-map-title"
        className="flex h-[min(92dvh,920px)] max-h-[92dvh] w-full max-w-[min(96vw,1180px)] flex-col overflow-hidden rounded-xl border border-rule bg-paper shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-rule px-4 py-3 sm:px-5">
          <div className="min-w-0">
            <h2
              id="relationship-map-title"
              className="font-serif text-lg text-ink"
              title="BM25 query matches and related pages from the crawl graph, with readable edge sampling."
            >
              Relationship map
            </h2>
            <p className="mt-0.5 truncate font-mono text-[11px] text-muted" title={q}>
              Query: <span className="text-ink">{q.trim() || "—"}</span>
              {jobId ? (
                <>
                  {" "}
                  · job <span className="text-ink">{jobId}</span>
                </>
              ) : null}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            title="Close the relationship map (Escape also closes)"
            className="shrink-0 rounded-lg border border-rule px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:border-accent hover:text-accent"
          >
            Close
          </button>
        </header>

        {raw?.message ? (
          <div className="shrink-0 border-b border-rule/80 bg-paper/80 px-4 py-2 font-mono text-[11px] text-muted sm:px-5">
            {raw.message}
          </div>
        ) : null}

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
          <div className="relative flex min-h-[52vh] flex-1 flex-col border-b border-rule lg:min-h-0 lg:border-b-0 lg:border-e">
            {loading ? (
              <div className="absolute inset-0 z-[1] flex items-center justify-center bg-paper/80 font-mono text-xs text-muted">
                Loading neighborhood…
              </div>
            ) : null}
            {errorMessage ? (
              <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-2 p-6 text-center">
                <p className="text-sm text-danger">{errorMessage}</p>
                <button
                  type="button"
                  title="Fetch the neighborhood graph again for this query and job."
                  onClick={() => {
                    setErrorMessage(null);
                    setRaw(null);
                    setLoading(true);
                    fetchGraphQuery({
                      q: q.trim(),
                      job_id: jobId ?? undefined,
                      max_seed_pages: 10,
                      radius: 1,
                      max_nodes: 50,
                    })
                      .then((res) => {
                        setRaw(res);
                        const types = new Set(res.edges.map((e) => e.edge_type));
                        const next: Record<string, boolean> = {};
                        Array.from(types).forEach((t) => {
                          next[t] = true;
                        });
                        setEdgeTypeOn(next);
                        setMinWeight(0);
                      })
                      .catch((err: unknown) => {
                        setErrorMessage(err instanceof Error ? err.message : "Failed to load graph.");
                      })
                      .finally(() => setLoading(false));
                  }}
                  className="rounded-lg border border-rule px-3 py-1.5 text-xs font-medium hover:border-accent"
                >
                  Retry
                </button>
              </div>
            ) : apiEmpty ? (
              <div className="flex h-full min-h-[240px] items-center p-4">
                <EmptyState
                  title="No graph nodes"
                  description="There are no BM25 hits or neighbors for this query in the selected corpus. Try another query or a different job."
                />
              </div>
            ) : filteredEmpty ? (
              <div className="flex h-full min-h-[240px] items-center p-4">
                <EmptyState
                  title="Nothing to show"
                  description="All nodes were hidden or every edge was filtered out. Loosen filters or show duplicate nodes."
                />
              </div>
            ) : (
              <div className="flex min-h-0 flex-1 flex-col">
                {showNoApiEdgesBanner ? (
                  <div
                    role="status"
                    className="shrink-0 border-b border-amber-500/25 bg-amber-500/[0.06] px-3 py-2.5 text-xs sm:px-4"
                  >
                    <p className="font-medium text-ink">Sparse graph</p>
                    <p className="mt-1 leading-relaxed text-muted">
                      No relationships found between the returned pages. Showing top query matches only.
                    </p>
                    <p className="mt-1.5 leading-relaxed text-[11px] text-muted">
                      Try increasing <span className="font-mono text-ink">radius</span> on the graph request if you need
                      more hops, or check that graph edge generation populated{" "}
                      <span className="font-mono text-ink">page_graph_edges</span> for this crawl.
                    </p>
                  </div>
                ) : null}
                {showFilteredEdgesBanner ? (
                  <div
                    role="status"
                    className="shrink-0 border-b border-rule/80 bg-paper/80 px-3 py-2 text-[11px] leading-snug text-muted sm:px-4"
                  >
                    All edges are hidden by filters (edge types or minimum weight). Loosen filters to see links.
                  </div>
                ) : null}
                <div
                  ref={wrapRef}
                  className="relative flex min-h-0 flex-1 flex-col bg-paper [&:fullscreen]:box-border [&:fullscreen]:max-h-none [&:fullscreen]:min-h-0 [&:fullscreen]:h-screen [&:fullscreen]:w-screen [&:fullscreen]:shrink"
                  title="Hover a node or edge to emphasize neighbors. Click a node for page details or an edge for evidence. Scroll to zoom if enabled by the graph control."
                >
                  <div className="pointer-events-none absolute right-2 top-2 z-[2] flex justify-end [&_button]:pointer-events-auto">
                    <button
                      type="button"
                      onClick={toggleGraphFullscreen}
                      title={graphIsFullscreen ? "Leave full screen" : "Full screen graph"}
                      aria-label={graphIsFullscreen ? "Leave full screen" : "Full screen graph"}
                      aria-pressed={graphIsFullscreen}
                      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border text-ink shadow-sm hover:border-accent ${
                        graphIsFullscreen
                          ? "border-rule/80 bg-paper/95 backdrop-blur-sm"
                          : "border-rule/70 bg-paper/90 backdrop-blur-[2px]"
                      }`}
                    >
                      {graphIsFullscreen ? <IconFullscreenExit /> : <IconFullscreenEnter />}
                    </button>
                  </div>
                  <ForceGraph2D
                    ref={fgRef}
                    width={dims.w}
                    height={dims.h}
                    backgroundColor={graphBg}
                    graphData={graphData}
                    nodeId="id"
                    linkSource="source"
                    linkTarget="target"
                    nodeLabel={(n) => nodeDisplayTitle(n as GraphQueryNodeRead)}
                    nodeVal={(n) => (n.role === "query_match" ? 8 : n.role === "related_neighbor" ? 2.5 : 1.5)}
                    nodeRelSize={4}
                    nodeCanvasObjectMode={() => "after"}
                    nodeCanvasObject={nodeCanvasObject}
                    nodeColor={(n) => {
                      const dim =
                        graphHasFocus &&
                        highlightNodeSet != null &&
                        !highlightNodeSet.has(n.page_id);
                      if (n.role === "query_match") {
                        return dim ? `rgba(${accentRgb}, 0.38)` : `rgb(${accentRgb})`;
                      }
                      if (n.role === "related_neighbor") {
                        return dim ? `rgba(${mutedRgb}, 0.22)` : `rgba(${mutedRgb}, 0.72)`;
                      }
                      return `rgba(${mutedRgb}, 0.35)`;
                    }}
                    linkColor={(l) => {
                      const s = linkEndpointId(l.source);
                      const t = linkEndpointId(l.target);
                      const selectedEdgeId = selection?.kind === "edge" ? selection.edge.edge_id : null;
                      const isSelectedEdge = selectedEdgeId != null && l.edge_id === selectedEdgeId;
                      const touchesSeed = highlightSeeds.has(s) || highlightSeeds.has(t);

                      if (!graphHasFocus) {
                        return edgeColorForType(l.edge_type, 0.2);
                      }
                      if (touchesSeed) {
                        const a = isSelectedEdge ? 0.98 : hoverLinkId === l.edge_id ? 0.95 : 0.88;
                        return edgeColorForType(l.edge_type, a);
                      }
                      return edgeColorForType(l.edge_type, 0.06);
                    }}
                    linkLineDash={(l) => edgeDashForType(l.edge_type)}
                    linkWidth={(l) => {
                      const s = linkEndpointId(l.source);
                      const t = linkEndpointId(l.target);
                      const selectedEdgeId = selection?.kind === "edge" ? selection.edge.edge_id : null;
                      const isSelectedEdge = selectedEdgeId != null && l.edge_id === selectedEdgeId;
                      const touchesSeed = highlightSeeds.has(s) || highlightSeeds.has(t);
                      const w = linkWidthScale(l.weight);
                      if (!graphHasFocus) return w;
                      if (isSelectedEdge) return w * 1.65;
                      if (touchesSeed) return w * 1.35;
                      return w * 0.75;
                    }}
                    linkDirectionalArrowLength={0}
                    enableNodeDrag={false}
                    minZoom={0.35}
                    maxZoom={6}
                    d3VelocityDecay={0.2}
                    warmupTicks={120}
                    cooldownTicks={160}
                    onEngineStop={onEngineStop}
                    onNodeHover={(node) => {
                      setHoverLinkId(null);
                      setHoverId(node ? (node as GraphQueryNodeRead).page_id : null);
                    }}
                    onLinkHover={(link) => {
                      setHoverId(null);
                      const l = link as GraphQueryEdgeRead | null;
                      setHoverLinkId(l?.edge_id ?? null);
                    }}
                    onNodeClick={(node) => {
                      setHoverLinkId(null);
                      setSelection({
                        kind: "node",
                        node: {
                          page_id: node.page_id,
                          title: node.title,
                          url: node.url,
                          normalized_url: node.normalized_url,
                          depth: node.depth,
                          role: node.role,
                          bm25_score: node.bm25_score,
                          metrics: node.metrics,
                          cluster_id: node.cluster_id,
                        },
                      });
                    }}
                    onLinkClick={(link) => {
                      setHoverLinkId(null);
                      const l = link as GraphQueryEdgeRead & { source?: unknown; target?: unknown };
                      const ends = normalizeLinkEndpoints(l);
                      const fromRaw = raw?.edges.find((e) => e.edge_id === l.edge_id);
                      setSelection({
                        kind: "edge",
                        edge:
                          fromRaw ??
                          ({
                            edge_id: l.edge_id,
                            edge_type: l.edge_type,
                            weight: l.weight,
                            evidence: l.evidence,
                            reason: (l as GraphQueryEdgeRead).reason,
                            ...ends,
                          } as GraphQueryEdgeRead),
                      });
                    }}
                    onBackgroundClick={() => {
                      setSelection(null);
                      setHoverId(null);
                      setHoverLinkId(null);
                    }}
                  />
                </div>
                <div className="min-h-0 shrink-0 border-t border-rule/80 bg-paper/50">
                  <p
                    className="border-b border-rule/60 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted sm:px-4"
                    title="Same nodes as in the graph, sorted with query matches first. Click a row to inspect it in the sidebar."
                  >
                    Pages in this map ({sortedPagesList.length})
                  </p>
                  <ul className="max-h-[min(22vh,200px)] overflow-y-auto overscroll-contain px-2 py-2 sm:px-3">
                    {sortedPagesList.map((n) => (
                      <li key={n.page_id} className="border-b border-rule/40 last:border-b-0">
                        <button
                          type="button"
                          onClick={() =>
                            setSelection({
                              kind: "node",
                              node: {
                                page_id: n.page_id,
                                title: n.title,
                                url: n.url,
                                normalized_url: n.normalized_url,
                                depth: n.depth,
                                role: n.role,
                                bm25_score: n.bm25_score,
                                metrics: n.metrics,
                                cluster_id: n.cluster_id,
                              },
                            })
                          }
                          className="w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-paper/80"
                        >
                          <span className="line-clamp-2 text-xs font-medium text-ink">{nodeDisplayTitle(n)}</span>
                          <span className="mt-0.5 block truncate font-mono text-[10px] text-muted" title={n.url}>
                            <span className="text-ink">{safeHostname(n.url)}</span>
                            <span className="text-rule"> — </span>
                            <span>{n.url}</span>
                          </span>
                          <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] uppercase tracking-wider text-muted">
                            <span className="text-ink">{n.role.replace(/_/g, " ")}</span>
                            {n.bm25_score != null ? (
                              <span>
                                BM25 <span className="text-ink">{n.bm25_score.toFixed(4)}</span>
                              </span>
                            ) : (
                              <span className="normal-case tracking-normal text-rule">No BM25 score</span>
                            )}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>

          <aside className="flex w-full max-h-[min(38vh,320px)] shrink-0 flex-col overflow-hidden border-t border-rule bg-paper/90 lg:max-h-none lg:min-h-0 lg:w-[min(100%,360px)] lg:max-w-[380px] lg:shrink-0 lg:self-stretch lg:border-l lg:border-t-0">
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {raw?.selected_job ? (
                <div
                  className="border-b border-accent/20 bg-accent/5 px-3 py-2 sm:px-4"
                  title="Which crawl job's pages and graph edges power this map. Explicit means you chose the job; otherwise the API may auto-pick a corpus."
                >
                  <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Corpus</p>
                  <p className="mt-1 text-sm text-ink">
                    Crawl job <span className="font-mono">{raw.selected_job.crawl_job_id}</span>
                    <span className="px-2 text-rule">·</span>
                    <span className="font-mono text-xs text-muted">{raw.selected_job.selection_mode}</span>
                  </p>
                  <p className="mt-1 text-xs leading-snug text-muted">{raw.selected_job.message}</p>
                </div>
              ) : null}

              <div className="space-y-2 border-b border-rule/70 px-3 py-2.5 sm:px-4">
                <p
                  className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted"
                  title="How many neighbor pages and how many edges per node appear in the mini map. Lower values keep the view readable; raise them to explore more of the crawl graph."
                >
                  Map density
                </p>
                <div className="flex flex-wrap gap-3">
                  <label
                    className="flex flex-col gap-1 font-mono text-[11px] text-muted"
                    title="Caps how many related_neighbor pages are shown with the query matches. Query matches are always included up to the API limit."
                  >
                    <span>Related nodes</span>
                    <select
                      value={relatedCap === "all" ? "all" : String(relatedCap)}
                      onChange={(e) => {
                        const v = e.target.value;
                        setRelatedCap(v === "all" ? "all" : (Number(v) as RelatedCapChoice));
                      }}
                      title="Maximum related neighbors in the map (BM25-ranked). All = no cap within API nodes."
                      className="h-9 rounded-lg border border-rule bg-paper px-2 text-xs text-ink"
                    >
                      {RELATED_CAP_OPTIONS.map((n) => (
                        <option key={n} value={String(n)}>
                          {n}
                        </option>
                      ))}
                      <option value="all">All</option>
                    </select>
                  </label>
                  <label
                    className="flex flex-col gap-1 font-mono text-[11px] text-muted"
                    title="After filters, each node keeps at most this many incident edges in the drawn map (greedy, type-prioritized). All = no per-node cap."
                  >
                    <span>Edges per node</span>
                    <select
                      value={edgesPerNode === "all" ? "all" : String(edgesPerNode)}
                      onChange={(e) => {
                        const v = e.target.value;
                        setEdgesPerNode(v === "all" ? "all" : (Number(v) as EdgesPerNodeChoice));
                      }}
                      title="Cap on drawn edges touching each visible node. Lower = cleaner map."
                      className="h-9 rounded-lg border border-rule bg-paper px-2 text-xs text-ink"
                    >
                      {EDGES_PER_NODE_OPTIONS.map((n) => (
                        <option key={n} value={String(n)}>
                          {n}
                        </option>
                      ))}
                      <option value="all">All</option>
                    </select>
                  </label>
                </div>
                {raw && raw.nodes.length > 0 && raw.edges.length > 0 ? (
                  <div
                    className="space-y-1 font-mono text-[11px] text-muted"
                    title="Nodes: visible in the map vs returned by the API. Edges: drawn in the map vs total API edges. The second line explains filtering between visible nodes (weight, type toggles, then per-node cap)."
                  >
                    <p>
                      Showing <span className="text-ink">{curatedNodes.length}</span> of{" "}
                      <span className="text-ink">{raw.nodes.length}</span> nodes ·{" "}
                      <span className="text-ink">{prunedLinks.length}</span> of{" "}
                      <span className="text-ink">{raw.edges.length}</span> API edges
                      {raw.edges.length > 0 ? (
                        <>
                          {" "}
                          (
                          <span className="text-ink">
                            {((100 * prunedLinks.length) / raw.edges.length).toFixed(
                              prunedLinks.length < raw.edges.length * 0.1 ? 2 : 1,
                            )}
                          </span>
                          % drawn)
                        </>
                      ) : null}
                      .
                    </p>
                    {edgeCountBeforePrune !== prunedLinks.length || edgesAfterFilters.length !== edgeCountBeforePrune ? (
                      <p className="text-[10px] leading-snug">
                        Between visible nodes: <span className="text-ink">{prunedLinks.length}</span> drawn
                        {edgeCountBeforePrune !== prunedLinks.length ? (
                          <>
                            {" "}
                            of <span className="text-ink">{edgeCountBeforePrune}</span> after filters
                          </>
                        ) : null}
                        {edgesAfterFilters.length !== edgeCountBeforePrune ? (
                          <>
                            {" "}
                            (<span className="text-ink">{edgesAfterFilters.length}</span> pass weight / type filters first)
                          </>
                        ) : null}
                        .
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {raw && raw.edges.length > VERY_DENSE_EDGE_THRESHOLD ? (
                  <p
                    className="text-[11px] leading-snug text-muted"
                    title="When the API returns many edges, content_similarity gets an automatic minimum weight so the map stays readable. Link and url_hierarchy edges use only this panel's min-weight slider and type checkboxes."
                  >
                    Dense graph: a higher <span className="font-mono text-ink">content_similarity</span> floor applies
                    automatically; <span className="font-mono text-ink">link</span> and{" "}
                    <span className="font-mono text-ink">url_hierarchy</span> edges still follow the min-weight slider only.
                    Increase related nodes or edges per node if you need more detail.
                  </p>
                ) : null}
              </div>

              <div className="space-y-3 border-b border-rule/70 px-3 py-2.5 sm:px-4">
                <p
                  className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted"
                  title="Filter which edges are considered before the map's per-node edge cap. Combine min weight, edge types, and duplicate visibility."
                >
                  Filters
                </p>

                <label
                  className="flex flex-col gap-1.5 font-mono text-[11px] text-muted"
                  title="Edges with weight below this value are hidden (after edge-type toggles). Applies to all edge types; very dense graphs may also enforce a higher floor for content_similarity only."
                >
                  <span>
                    Min edge weight <span className="text-ink">{minWeight.toFixed(3)}</span>
                  </span>
                  <input
                    type="range"
                    min={weightExtent.min}
                    max={weightExtent.max}
                    step={(weightExtent.max - weightExtent.min) / 200 || 0.001}
                    value={Math.min(weightExtent.max, Math.max(weightExtent.min, minWeight))}
                    onChange={(e) => {
                      setMinWeight(Number(e.target.value));
                    }}
                    disabled={!raw?.edges.length}
                    title={`Edge weights in this response range from ${weightExtent.min.toFixed(4)} to ${weightExtent.max.toFixed(4)}. Drag right to show fewer, stronger edges.`}
                    className="h-1.5 w-full accent-accent"
                  />
                </label>

                {edgeTypes.length > 0 ? (
                  <fieldset
                    className="flex flex-wrap gap-x-4 gap-y-1.5"
                    title="Turn edge categories on or off. Disabled types are excluded from filtered counts and from the drawn map."
                  >
                    <legend className="sr-only">Edge types</legend>
                    {edgeTypes.map((t) => (
                      <label
                        key={t}
                        className="flex cursor-pointer items-center gap-1.5 font-mono text-[11px] text-ink"
                        title={tooltipForEdgeType(t)}
                      >
                        <input
                          type="checkbox"
                          checked={Boolean(edgeTypeOn[t])}
                          onChange={(e) => setEdgeTypeOn((prev) => ({ ...prev, [t]: e.target.checked }))}
                          title={tooltipForEdgeType(t)}
                          className="accent-accent"
                        />
                        <span
                          className="inline-block h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: edgeColorForType(t, 0.88) }}
                          aria-hidden
                        />
                        {t.replace(/_/g, " ")}
                      </label>
                    ))}
                  </fieldset>
                ) : null}

                <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5">
                  <label
                    className="flex cursor-pointer items-center gap-2 font-mono text-[11px] text-ink"
                    title="Duplicate cluster members are hidden from the map and list when checked. Turn off to see duplicate role nodes from the API."
                  >
                    <input
                      type="checkbox"
                      checked={hideDuplicateNodes}
                      onChange={(e) => setHideDuplicateNodes(e.target.checked)}
                      className="accent-accent"
                    />
                    Hide duplicate nodes
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => applyRingInitialLayout()}
                      title="Re-seed node positions on concentric rings and re-run the force simulation. Use if the graph feels stuck in a clump."
                      className="rounded-lg border border-rule px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wider text-ink hover:border-accent"
                    >
                      Reset layout
                    </button>
                    <button
                      type="button"
                      onClick={() => fgRef.current?.zoomToFit(400, 36)}
                      title="Zoom and pan so all visible nodes fit in the graph viewport."
                      className="rounded-lg border border-rule px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wider text-ink hover:border-accent"
                    >
                      Fit view
                    </button>
                  </div>
                </div>
              </div>

              <div className="px-3 py-3 sm:px-4">
                <p
                  className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted"
                  title="Summary of the loaded graph: node and edge counts, caps, and dense-graph rules. Click a node or edge on the map to see details here."
                >
                  Inspector
                </p>
                {!selection ? (
                graphSummary ? (
                  <div className="mt-2 space-y-3 text-xs">
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 font-mono text-[11px]">
                      <dt className="text-muted">Nodes (API / visible)</dt>
                      <dd className="text-ink">
                        {graphSummary.apiNodeCount} / {graphSummary.visibleNodeCount}
                      </dd>
                      <dt className="text-muted">Edges (API / filtered / drawn)</dt>
                      <dd className="text-ink">
                        {graphSummary.apiEdgeCount} / {graphSummary.edgeCountAfterFilters} / {graphSummary.edgeCountVisible}{" "}
                        <span className="text-muted">
                          (
                          {graphSummary.drawnEdgePct < 10
                            ? graphSummary.drawnEdgePct.toFixed(2)
                            : graphSummary.drawnEdgePct.toFixed(1)}
                          % drawn)
                        </span>
                      </dd>
                      <dt className="text-muted">Query matches</dt>
                      <dd className="text-ink">{graphSummary.queryMatches}</dd>
                      <dt className="text-muted">Related neighbors (visible)</dt>
                      <dd className="text-ink">{graphSummary.relatedNeighbors}</dd>
                      <dt className="text-muted">Min weight (slider)</dt>
                      <dd className="text-ink">{graphSummary.minWeightActive.toFixed(4)}</dd>
                      <dt className="text-muted">Similarity floor</dt>
                      <dd className="text-ink">
                        {graphSummary.contentSimilarityFloor > 0
                          ? graphSummary.apiEdgeCount > VERY_DENSE_EDGE_THRESHOLD
                            ? `content_similarity ≥ ${graphSummary.contentSimilarityFloor.toFixed(2)} (very dense)`
                            : `content_similarity ≥ ${graphSummary.contentSimilarityFloor.toFixed(2)} (dense)`
                          : "— (not applied for this edge count)"}
                      </dd>
                      {graphSummary.densePruningActive ? (
                        <>
                          <dt className="text-muted">Dense pruning</dt>
                          <dd className="text-ink">Active (API edges &gt; {VERY_DENSE_EDGE_THRESHOLD})</dd>
                        </>
                      ) : null}
                      <dt className="text-muted">Edges / node cap</dt>
                      <dd className="text-ink">{graphSummary.edgesPerNodeCap === "all" ? "All" : graphSummary.edgesPerNodeCap}</dd>
                      <dt className="text-muted">Related cap</dt>
                      <dd className="text-ink">{graphSummary.relatedNeighborCap === "all" ? "All" : graphSummary.relatedNeighborCap}</dd>
                      {graphSummary.duplicateNodes > 0 ? (
                        <>
                          <dt className="text-muted">Duplicates (API view)</dt>
                          <dd className="text-ink">{graphSummary.duplicateNodes}</dd>
                        </>
                      ) : null}
                    </dl>
                    <p
                      className="border-t border-rule/60 pt-2 text-[11px] leading-relaxed text-muted"
                      title="Selection drives the inspector panel. Clear selection by clicking the map background."
                    >
                      Click a node or list row for page details, or an edge for evidence. Hover a node or edge to dim
                      non-neighbors and emphasize incident links.
                    </p>
                  </div>
                ) : (
                  <p className="mt-2 text-xs leading-relaxed text-muted">
                    {loading
                      ? "Loading graph summary…"
                      : errorMessage
                        ? "Summary appears after a successful load."
                        : "Open the map after running a search to see a summary here."}
                  </p>
                )
              ) : selection.kind === "node" ? (
                <div className="mt-2 space-y-2 text-xs">
                  <p className="font-mono text-[10px] uppercase text-muted">{selection.node.role.replace(/_/g, " ")}</p>
                  <a
                    href={selection.node.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block font-medium text-accent underline decoration-rule underline-offset-2"
                  >
                    {selection.node.title ?? "Untitled page"}
                  </a>
                  <p className="break-all font-mono text-[10px] text-muted">{selection.node.url}</p>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 font-mono text-[11px]">
                    <dt className="text-muted">page_id</dt>
                    <dd className="text-ink">{selection.node.page_id}</dd>
                    {selection.node.bm25_score != null ? (
                      <>
                        <dt className="text-muted">BM25</dt>
                        <dd className="text-ink">{selection.node.bm25_score.toFixed(4)}</dd>
                      </>
                    ) : null}
                    <dt className="text-muted">depth</dt>
                    <dd className="text-ink">{selection.node.depth}</dd>
                  </dl>
                </div>
              ) : (
                <div className="mt-2 space-y-2 text-xs">
                  <p className="font-mono text-[10px] uppercase text-muted">Edge</p>
                  <p className="font-mono text-ink">{selection.edge.edge_type.replace(/_/g, " ")}</p>
                  <p className="leading-relaxed text-ink">{displayEdgeReason(selection.edge)}</p>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 font-mono text-[11px]">
                    <dt className="text-muted">edge_id</dt>
                    <dd className="text-ink">{selection.edge.edge_id}</dd>
                    <dt className="text-muted">weight</dt>
                    <dd className="text-ink">{selection.edge.weight.toFixed(4)}</dd>
                    <dt className="text-muted">source</dt>
                    <dd className="text-ink">{selection.edge.source_page_id}</dd>
                    <dt className="text-muted">target</dt>
                    <dd className="text-ink">{selection.edge.target_page_id}</dd>
                  </dl>
                  <details className="rounded border border-rule/70 bg-paper/40 [&_summary]:cursor-pointer [&_summary]:list-none">
                    <summary className="px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider text-muted">
                      Raw evidence (JSON)
                    </summary>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words border-t border-rule/60 p-2 font-mono text-[10px] leading-relaxed text-ink">
                      {formatEvidence(selection.edge.evidence)}
                    </pre>
                  </details>
                </div>
              )}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
