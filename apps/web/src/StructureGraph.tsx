import { useEffect, useMemo, useRef, useState } from 'react';

export type StructureLink = { name: string; viaJoint?: { name: string; kind: string }; children: StructureLink[] };
export type StructureSelection = { type: 'link' | 'joint'; name: string } | null;
type GraphNode = { id: string; type: 'link' | 'joint'; name: string; kind?: string; x: number; y: number };
type GraphEdge = { from: string; to: string };
const SPACING = 190;
const LEVEL = 148;

function layout(roots: StructureLink[]) {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  let leaf = 0;
  const walk = (link: StructureLink, depth: number): number => {
    const childPositions = link.children.map(child => walk(child, depth + 1));
    const x = childPositions.length ? (childPositions[0] + childPositions[childPositions.length - 1]) / 2 : 110 + leaf++ * SPACING;
    const id = 'link:' + link.name;
    nodes.push({ id, type: 'link', name: link.name, x, y: 106 + depth * LEVEL });
    for (let i = 0; i < link.children.length; i++) {
      const child = link.children[i];
      if (!child.viaJoint) continue;
      const jointId = 'joint:' + child.viaJoint.name;
      nodes.push({ id: jointId, type: 'joint', name: child.viaJoint.name,
        kind: child.viaJoint.kind, x: childPositions[i], y: 106 + depth * LEVEL + LEVEL / 2 });
      edges.push({ from: id, to: jointId }, { from: jointId, to: 'link:' + child.name });
    }
    return x;
  };
  roots.forEach(root => walk(root, 0));
  const width = Math.max(340, 220 + Math.max(0, leaf - 1) * SPACING);
  const height = Math.max(270, ...nodes.map(node => node.y + 80));
  return { nodes, edges, width, height };
}

export function StructureGraph({ roots, selected, onSelect, jointValues, angleUnit }: {
  roots: StructureLink[]; selected: StructureSelection;
  onSelect: (type: 'link' | 'joint', name: string) => void;
  jointValues: Record<string, { value: number; unit: string }>; angleUnit: 'rad' | 'deg';
}) {
  const graph = useMemo(() => layout(roots), [roots]);
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  useEffect(() => {
    const zoom = Math.min(2, Math.max(1, graph.width / 850));
    setView({ x: graph.width * (1 - 1 / zoom) / 2, y: 0, zoom });
  }, [graph]);
  const drag = useRef<{ x: number; y: number; originX: number; originY: number } | null>(null);
  const positions = new Map(graph.nodes.map(node => [node.id, node]));
  const zoomTo = (next: number) => setView(current => ({ ...current, zoom: Math.max(0.35, Math.min(5, next)) }));
  const viewWidth = graph.width / view.zoom;
  const viewHeight = graph.height / view.zoom;
  return <div className="structure-graph">
    <div className="structure-graph-tools">
      <span>拖动空白处平移 · 滚轮缩放 · 点击节点定位</span>
      <button type="button" onClick={() => zoomTo(view.zoom * 1.25)} aria-label="放大结构图">＋</button>
      <button type="button" onClick={() => zoomTo(view.zoom / 1.25)} aria-label="缩小结构图">－</button>
      <button type="button" onClick={() => setView({ x: 0, y: 0, zoom: 1 })}>适合视图</button>
    </div>
    <svg className="structure-graph-canvas" role="img" aria-label="机器人 Link 和 Joint 节点关系图"
      viewBox={`${view.x} ${view.y} ${viewWidth} ${viewHeight}`}
      onWheel={event => { event.preventDefault(); zoomTo(view.zoom * (event.deltaY < 0 ? 1.13 : 1 / 1.13)); }}
      onPointerDown={event => {
        if (event.button !== 0 || event.target !== event.currentTarget) return;
        drag.current = { x: event.clientX, y: event.clientY, originX: view.x, originY: view.y };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event => {
        if (!drag.current) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        const gesture = drag.current;
        const deltaX = event.clientX - gesture.x;
        const deltaY = event.clientY - gesture.y;
        setView(current => ({ ...current,
          x: gesture.originX - deltaX * (graph.width / current.zoom) / Math.max(1, bounds.width),
          y: gesture.originY - deltaY * (graph.height / current.zoom) / Math.max(1, bounds.height) }));
      }}
      onPointerUp={() => { drag.current = null; }}
      onLostPointerCapture={() => { drag.current = null; }}>
      {roots.length === 1 && <g className="structure-graph-ground">
        <path d={`M ${positions.get('link:' + roots[0].name)?.x ?? 110} 42 V 82`} />
        <rect x={(positions.get('link:' + roots[0].name)?.x ?? 110) - 64} y="7" width="128" height="36" rx="9" />
        <text x={positions.get('link:' + roots[0].name)?.x ?? 110} y="31" textAnchor="middle">Ground</text>
      </g>}
      {graph.edges.map((edge, index) => {
        const start = positions.get(edge.from); const end = positions.get(edge.to);
        if (!start || !end) return null;
        const sy = start.y + (start.type === 'link' ? 22 : 17);
        const ey = end.y - (end.type === 'link' ? 22 : 17);
        return <path key={index} className="structure-graph-edge" d={`M ${start.x} ${sy} V ${(sy + ey) / 2} H ${end.x} V ${ey}`} />;
      })}
      {graph.nodes.map(node => {
        const active = selected?.type === node.type && selected.name === node.name;
        const width = node.type === 'link' ? 150 : 146;
        const height = node.type === 'link' ? 44 : 50;
        return <g key={node.id} className={'structure-graph-node ' + node.type + (active ? ' selected' : '')}
          data-structure-node={node.id} role="button" tabIndex={0} aria-label={`${node.type === 'link' ? 'Link' : 'Joint'} ${node.name}`}
          aria-pressed={active} onClick={() => onSelect(node.type, node.name)}
          onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(node.type, node.name); } }}>
          <title>{node.name}{node.kind ? ' · ' + node.kind : ''}</title>
          <rect x={node.x - width / 2} y={node.y - height / 2} width={width} height={height} rx={node.type === 'joint' ? 17 : 9} />
          <text x={node.x} y={node.y + (node.kind ? -11 : 4)} textAnchor="middle">{node.name.length > 19 ? node.name.slice(0, 18) + '…' : node.name}</text>
          {node.kind && <text className="kind" x={node.x} y={node.y + 2} textAnchor="middle">{node.kind}</text>}
          {node.type === 'joint' && jointValues[node.name] && <text className="joint-value" x={node.x} y={node.y + 16} textAnchor="middle">
            {jointValues[node.name].unit === 'm' ? `${jointValues[node.name].value.toFixed(3)} m` :
              angleUnit === 'deg' ? `${(jointValues[node.name].value * 180 / Math.PI).toFixed(1)}°` : `${jointValues[node.name].value.toFixed(3)} rad`}
          </text>}
        </g>;
      })}
    </svg>
  </div>;
}
