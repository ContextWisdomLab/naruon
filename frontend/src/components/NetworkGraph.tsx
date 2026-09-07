'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Network } from 'vis-network';

interface Node {
  id: number | string;
  label: string;
  [key: string]: unknown;
}

interface Edge {
  id?: number | string;
  from: number | string;
  to: number | string;
  [key: string]: unknown;
}

interface ApiEdge {
  from?: number | string;
  to?: number | string;
  source?: number | string;
  target?: number | string;
  [key: string]: unknown;
}

interface NetworkData {
  nodes: Node[];
  edges: ApiEdge[];
}

interface NormalizedNetworkData {
  nodes: Node[];
  edges: Edge[];
}

interface GraphSelectionEvent {
  nodes?: Array<number | string>;
  edges?: Array<number | string>;
}

function textOnlyTooltip(value: unknown): HTMLElement {
  const tooltip = document.createElement('div');
  tooltip.textContent = value == null ? '' : String(value);
  return tooltip;
}

const HTML_TEXT_ESCAPE_PATTERN = /[&<>"']/g;
const HTML_TEXT_ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

function escapeGraphLabel(value: unknown): string {
  return String(value ?? '').replace(
    HTML_TEXT_ESCAPE_PATTERN,
    (character) => HTML_TEXT_ESCAPES[character] ?? character,
  );
}

function sanitizeGraphItem<T extends Node | Edge>(item: T): T {
  const sanitized = { ...item };

  if (Object.prototype.hasOwnProperty.call(item, 'title')) {
    sanitized.title = textOnlyTooltip(item.title);
  }

  return sanitized;
}

function escapeVisNetworkLabels<T extends Node | Edge>(items: T[]): T[] {
  return items.map((item) => {
    if (!Object.prototype.hasOwnProperty.call(item, 'label')) return item;
    return {
      ...item,
      label: escapeGraphLabel(item.label),
    };
  });
}

function isGraphId(value: unknown): value is number | string {
  return typeof value === 'number' || typeof value === 'string';
}

function stableEdgeId(edge: Edge, index: number) {
  if (isGraphId(edge.id)) return edge.id;
  return `relationship-${index}-${String(edge.from)}-${String(edge.to)}`;
}

function normalizeEdge(edge: ApiEdge): Edge | null {
  const from = edge.from ?? edge.source;
  const to = edge.to ?? edge.target;

  if (!isGraphId(from) || !isGraphId(to)) return null;

  const rest = { ...edge };
  delete rest.source;
  delete rest.target;
  return {
    ...rest,
    from,
    to,
  };
}

function sanitizeNetworkData(data: NetworkData): NormalizedNetworkData {
  return {
    nodes: data.nodes.map(sanitizeGraphItem),
    edges: data.edges.flatMap((edge, index) => {
      const normalized = normalizeEdge(edge);
      return normalized ? [sanitizeGraphItem({ ...normalized, id: stableEdgeId(normalized, index) })] : [];
    }),
  };
}

function titleText(value: unknown) {
  if (typeof HTMLElement !== 'undefined' && value instanceof HTMLElement) {
    return value.textContent?.trim() ?? '';
  }
  return value == null ? '' : String(value).trim();
}

/**
 * Index graph records by public id, keeping the first instance.
 *
 * `new Map(items.map((item) => [String(item.id), item]))` is last-wins and
 * desynchronizes first-wins label maps from the selected node or edge when
 * the API repeats an id. The previous `.find()` selection path was first-wins.
 */
function firstGraphEntryById<T>(
  items: readonly T[],
  readId: (item: T) => unknown,
): Map<string, T> {
  const map = new Map<string, T>();
  for (const item of items) {
    const rawId = readId(item);
    if (!isGraphId(rawId)) {
      continue;
    }
    const key = String(rawId);
    if (!map.has(key)) {
      map.set(key, item);
    }
  }
  return map;
}

function describeEdge(edge: Edge, nodeMap: Map<string | number, string>) {
  const fromLabel = nodeMap.get(String(edge.from)) ?? String(edge.from);
  const toLabel = nodeMap.get(String(edge.to)) ?? String(edge.to);
  const title = titleText(edge.title);
  return title ? `${fromLabel} -> ${toLabel} (${title})` : `${fromLabel} -> ${toLabel}`;
}

import { apiClient } from '@/lib/api-client';

export default function NetworkGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const unavailableRelationshipDescriptionId = useId();

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedGraphDetail, setSelectedGraphDetail] = useState<string | null>(null);
  const [graphActionStatus, setGraphActionStatus] = useState('그래프 준비 완료');
  const [relationshipOptionId, setRelationshipOptionId] = useState('');
  const [nodeOptionId, setNodeOptionId] = useState('');
  const edgeMap = useMemo(() => firstGraphEntryById(edges, (edge) => edge.id), [edges]);
  const nodeInstanceMap = useMemo(() => firstGraphEntryById(nodes, (node) => node.id), [nodes]);
  const nodeMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const node of nodes) {
      const key = String(node.id);
      if (!map.has(key)) {
        map.set(key, String(node.label ?? node.id));
      }
    }
    return map;
  }, [nodes]);

  useEffect(() => {
    apiClient.get<NetworkData>('/api/network/graph')
      .then((data) => {
        const sanitized = sanitizeNetworkData(data);
        setNodes(sanitized.nodes);
        setEdges(sanitized.edges);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load network graph:', err);
        setError('관계 맥락을 불러오지 못했습니다.');
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (containerRef.current && nodes.length > 0) {
      const container = containerRef.current;
      const network = new Network(container, {
        nodes: escapeVisNetworkLabels(nodes),
        edges: escapeVisNetworkLabels(edges),
      }, {
        nodes: { shape: 'dot', size: 16 },
        edges: { arrows: 'to' }
      });
      networkRef.current = network;

      const fitGraph = () => {
        network.fit?.({ animation: false });
      };

      const selectEdge = (edgeId: number | string) => {
        const edge = edgeMap.get(String(edgeId));
        if (!edge) return;
        setRelationshipOptionId(String(edge.id));
        setNodeOptionId('');
        setSelectedGraphDetail(`선택된 관계: ${describeEdge(edge, nodeMap)}`);
        setGraphActionStatus('그래프에서 관계를 선택했습니다.');
      };

      const selectNode = (nodeId: number | string) => {
        setRelationshipOptionId('');
        setNodeOptionId(String(nodeId));
        setSelectedGraphDetail(`선택된 노드: ${nodeMap.get(String(nodeId)) ?? String(nodeId)}`);
        setGraphActionStatus('그래프에서 노드를 선택했습니다.');
      };

      const handleEdgeSelection = (event: GraphSelectionEvent) => {
        const edgeId = event.edges?.[0];
        if (isGraphId(edgeId)) selectEdge(edgeId);
      };

      const handleNodeSelection = (event: GraphSelectionEvent) => {
        const nodeId = event.nodes?.[0];
        if (isGraphId(nodeId)) selectNode(nodeId);
      };

      const canListenForSelection =
        typeof network.on === 'function' && typeof network.off === 'function';

      if (canListenForSelection) {
        network.on('selectEdge', handleEdgeSelection);
        network.on('selectNode', handleNodeSelection);
      }

      let resizeTimer: ReturnType<typeof setTimeout> | null = null;
      const resizeObserver = typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            if (resizeTimer !== null) {
              clearTimeout(resizeTimer);
            }
            resizeTimer = setTimeout(fitGraph, 50);
          });

      resizeObserver?.observe(container);

      return () => {
        if (resizeTimer !== null) {
          clearTimeout(resizeTimer);
        }
        resizeObserver?.disconnect();
        if (canListenForSelection) {
          network.off('selectEdge', handleEdgeSelection);
          network.off('selectNode', handleNodeSelection);
        }
        if (networkRef.current === network) {
          networkRef.current = null;
        }
        network.destroy();
      };
    }
  }, [nodes, edges, nodeMap, edgeMap]);

  const nodeLabels = useMemo(() => {
    const labels: string[] = [];
    for (const node of nodes) {
      if (labels.length >= 5) break;
      const label = String(node.label ?? node.id);
      if (label) labels.push(label);
    }
    return labels;
  }, [nodes]);

  const firstEdge = edges[0] ?? null;
  const relationshipOptions = useMemo(() => {
    const options = [];
    let index = 0;
    for (const edge of edgeMap.values()) {
      if (options.length >= 5) break;
      options.push({
        edge,
        id: String(edge.id),
        label: `관계 ${index + 1}: ${describeEdge(edge, nodeMap)}`,
      });
      index++;
    }
    return options;
  }, [edgeMap, nodeMap]);

  const nodeOptions = useMemo(() => {
    const options = [];
    for (const node of nodeInstanceMap.values()) {
      if (options.length >= 8) break;
      options.push({
        id: String(node.id),
        label: `노드: ${String(node.label ?? node.id)}`,
        node,
      });
    }
    return options;
  }, [nodeInstanceMap]);

  const selectRelationship = (edge: Edge, status: string) => {
    setRelationshipOptionId(String(edge.id));
    setNodeOptionId('');
    setSelectedGraphDetail(`선택된 관계: ${describeEdge(edge, nodeMap)}`);
    setGraphActionStatus(status);
    if (isGraphId(edge.id)) {
      networkRef.current?.selectEdges?.([edge.id]);
    }
    networkRef.current?.fit?.({ nodes: [edge.from, edge.to], animation: false });
  };

  const selectGraphNode = (node: Node, status: string) => {
    if (!isGraphId(node.id)) return;
    setRelationshipOptionId('');
    setNodeOptionId(String(node.id));
    setSelectedGraphDetail(`선택된 노드: ${nodeMap.get(String(node.id)) ?? String(node.id)}`);
    setGraphActionStatus(status);
    networkRef.current?.selectNodes?.([node.id]);
    networkRef.current?.fit?.({ nodes: [node.id], animation: false });
  };

  const handleSelectFirstRelationship = () => {
    if (!firstEdge) return;
    selectRelationship(firstEdge, '첫 관계를 선택했습니다.');
  };

  const handleRelationshipOptionChange = (value: string) => {
    const edge = edgeMap.get(value);
    if (!edge) return;
    selectRelationship(edge, '선택한 관계를 열었습니다.');
  };

  const handleNodeOptionChange = (value: string) => {
    const node = nodeInstanceMap.get(value);
    if (!node) return;
    selectGraphNode(node, '선택한 노드를 열었습니다.');
  };

  const handleZoomGraph = () => {
    networkRef.current?.moveTo?.({ scale: 1.15, animation: false });
    setGraphActionStatus('그래프 확대 완료');
  };

  const handleFitGraph = () => {
    networkRef.current?.fit?.({ animation: false });
    setGraphActionStatus('그래프 맞춤 완료');
  };

  if (loading) {
    return <div role="status" aria-live="polite" className="flex h-full min-h-[320px] w-full items-center justify-center text-sm text-muted-foreground sm:min-h-[420px]">관계 맥락을 불러오는 중입니다...</div>;
  }

  if (error) {
    return (
      <div role="alert" aria-live="polite" className="flex h-full min-h-[320px] w-full items-center justify-center p-6 text-center sm:min-h-[420px]">
        <div className="max-w-xs rounded-2xl border border-red-200 bg-red-50 p-5 text-red-700">
          <h4 className="font-bold">관계 맥락을 불러오지 못했습니다</h4>
          <p className="mt-2 text-sm leading-6">{error}</p>
        </div>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div role="status" aria-live="polite" className="flex h-full min-h-[320px] w-full items-center justify-center p-6 text-center sm:min-h-[420px]">
        <div className="max-w-xs rounded-2xl border border-primary/15 bg-primary/5 p-5">
          <div className="mx-auto mb-3 grid size-12 place-items-center rounded-2xl bg-primary/10 text-2xl" aria-hidden="true">✦</div>
          <h4 className="font-bold text-foreground">관계 데이터가 없습니다</h4>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">메일이 연결되면 사람, 주제, 일정의 흐름을 관계 맥락으로 보여줍니다.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[320px] flex-col sm:min-h-[420px]">
      <div className="border-b border-border bg-card/80 p-4">
        <h4 className="text-sm font-black text-foreground">관계 이해</h4>
        <p className="mt-1 text-xs text-muted-foreground">
          {nodes.length}개 노드와 {edges.length}개 관계가 이 스레드 맥락에 연결되어 있습니다.
        </p>
        <div className="mt-3 rounded-xl border border-primary/10 bg-primary/5 p-3 text-xs text-muted-foreground">
          <p className="font-semibold text-foreground">텍스트 관계 맥락 종합</p>
          <p className="mt-1">
            관련 노드: {nodeLabels.join(', ')}
          </p>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <span
            tabIndex={!firstEdge ? 0 : undefined}
            aria-describedby={!firstEdge ? unavailableRelationshipDescriptionId : undefined}
            title={!firstEdge ? "표시할 관계 데이터가 없습니다." : undefined}
            className={
              !firstEdge
                ? "cursor-not-allowed rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                : undefined
            }
          >
            {!firstEdge && (
              <span id={unavailableRelationshipDescriptionId} className="sr-only">
                표시할 관계 데이터가 없습니다.
              </span>
            )}
            <button
              type="button"
              onClick={handleSelectFirstRelationship}
              disabled={!firstEdge}
              className={`rounded-md border border-primary/25 bg-background px-3 py-2 text-xs font-bold text-primary transition hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50 ${!firstEdge ? "pointer-events-none" : ""}`}
            >
              첫 관계 보기
            </button>
          </span>
          <button
            type="button"
            onClick={handleZoomGraph}
            className="rounded-md border border-border bg-background px-3 py-2 text-xs font-bold text-foreground transition hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            그래프 확대
          </button>
          <button
            type="button"
            onClick={handleFitGraph}
            className="rounded-md border border-border bg-background px-3 py-2 text-xs font-bold text-foreground transition hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            전체 그래프 맞춤
          </button>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="text-xs font-bold text-foreground">
            관계 선택
            <select
              aria-label="관계 선택"
              value={relationshipOptionId}
              onChange={(event) => handleRelationshipOptionChange(event.target.value)}
              className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-xs font-semibold text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <option value="">관계 선택</option>
              {relationshipOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-bold text-foreground">
            노드 선택
            <select
              aria-label="노드 선택"
              value={nodeOptionId}
              onChange={(event) => handleNodeOptionChange(event.target.value)}
              className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-xs font-semibold text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <option value="">노드 선택</option>
              {nodeOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div aria-live="polite" className="mt-3 rounded-md border border-border bg-background p-3 text-xs text-muted-foreground">
          <p className="font-semibold text-foreground">관계 상세</p>
          <p className="mt-1">
            {selectedGraphDetail ?? '관계를 선택하면 담당자와 일정 흐름을 확인합니다.'}
          </p>
          <p className="mt-1 font-medium text-primary">{graphActionStatus}</p>
        </div>
      </div>
      <div
        ref={containerRef}
        aria-label={`${nodes.length}개 노드와 ${edges.length}개 관계가 있는 관계 맥락`}
        className="min-h-0 flex-1 w-full bg-[radial-gradient(circle_at_center,rgb(37_99_255_/_0.08),transparent_32rem)]"
      />
    </div>
  );
}
