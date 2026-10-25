import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

let nextLayer = 20;
type Rect = { x: number; y: number; width: number; height: number };
type DockSide = 'left' | 'right';
type Placement = 'dock' | 'free' | 'left' | 'right' | 'bottom';
type DockTargets = { left: HTMLDivElement | null; right: HTMLDivElement | null };
const DockContext = createContext<DockTargets | null>(null);

export function PanelDockProvider({ children, className = '' }: { children: ReactNode; className?: string }) {
  const [left, setLeft] = useState<HTMLDivElement | null>(null);
  const [right, setRight] = useState<HTMLDivElement | null>(null);
  return <DockContext.Provider value={{ left, right }}>
    {children}
    <div ref={setLeft} className={`panel-dock panel-dock-left ${className}`} aria-label="左侧工具栏" />
    <div ref={setRight} className={`panel-dock panel-dock-right ${className}`} aria-label="右侧工具栏" />
  </DockContext.Provider>;
}

export function FloatingPanel({ title, initial, children, onClose, className = '', dockSide, dockOrder = 0 }: {
  title: string; initial: Rect; children: ReactNode; onClose?: () => void;
  className?: string; dockSide?: DockSide; dockOrder?: number;
}) {
  const docks = useContext(DockContext);
  const dockTarget = dockSide ? docks?.[dockSide] : null;
  const [position, setPosition] = useState({ x: initial.x, y: initial.y });
  const [size, setSize] = useState({ width: initial.width, height: initial.height });
  const [placement, setPlacement] = useState<Placement>(dockSide ? 'dock' : 'free');
  const [menuOpen, setMenuOpen] = useState(false);
  const [layer, setLayer] = useState(++nextLayer);
  const initialArea = useRef(Math.max(1, initial.width * initial.height));
  const restore = useRef<{ placement: Placement; rect: Rect } | null>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number; docked: boolean; moved: boolean } | null>(null);
  const resize = useRef<{ direction: string; x: number; y: number; rect: Rect; docked: boolean } | null>(null);
  const frame = useRef<HTMLElement | null>(null);
  const expanded = placement === 'left' || placement === 'right' || placement === 'bottom';

  function workspaceRect(mode: 'left' | 'right' | 'bottom'): Rect | null {
    const root = frame.current?.closest('.viewer-workspace, .cad-full-workspace') as HTMLElement | null;
    if (!root) return null;
    const bounds = root.getBoundingClientRect();
    const dockTop = docks?.left?.getBoundingClientRect().top ?? bounds.top + 8;
    const top = Math.max(bounds.top + 8, dockTop);
    const height = Math.max(125, bounds.bottom - top - 8);
    const width = Math.max(220, Math.floor((bounds.width - 24) / 4));
    if (mode === 'bottom') return { x: bounds.left + 8, y: bounds.bottom - Math.max(125, height / 4) - 8,
      width: bounds.width - 16, height: Math.max(125, height / 4) };
    return { x: mode === 'left' ? bounds.left + 8 : bounds.right - width - 8,
      y: top, width, height };
  }
  function setQuarter(mode: 'left' | 'right' | 'bottom') {
    const rect = workspaceRect(mode);
    if (!rect) return;
    if (!expanded) {
      const bounds = frame.current?.getBoundingClientRect();
      restore.current = { placement, rect: placement === 'dock' && bounds ?
        { x: bounds.left, y: bounds.top, width: bounds.width, height: bounds.height } :
        { x: position.x, y: position.y, width: size.width, height: size.height } };
    }
    setPosition({ x: rect.x, y: rect.y });
    setSize({ width: rect.width, height: rect.height });
    setPlacement(mode);
    setMenuOpen(false);
    setLayer(++nextLayer);
  }
  function restorePanel() {
    const previous = restore.current;
    if (previous) {
      setPlacement(previous.placement);
      setPosition({ x: previous.rect.x, y: previous.rect.y });
      setSize({ width: previous.rect.width, height: previous.rect.height });
    } else setPlacement(dockSide ? 'dock' : 'free');
    setMenuOpen(false);
  }
  useEffect(() => {
    if (!expanded) return;
    const update = () => {
      const rect = workspaceRect(placement);
      if (rect) { setPosition({ x: rect.x, y: rect.y }); setSize({ width: rect.width, height: rect.height }); }
    };
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [placement, expanded]);
  function resizeMove(event: React.PointerEvent<HTMLSpanElement>) {
    const active = resize.current;
    if (!active || expanded) return;
    if (active.docked) setPlacement('free');
    const viewport = active.docked || !!dockSide;
    const maxWidth = viewport ? window.innerWidth : frame.current?.parentElement?.clientWidth ?? window.innerWidth;
    const maxHeight = viewport ? window.innerHeight : frame.current?.parentElement?.clientHeight ?? window.innerHeight;
    const dx = event.clientX - active.x;
    const dy = event.clientY - active.y;
    let left = active.rect.x;
    let top = active.rect.y;
    let right = active.rect.x + active.rect.width;
    let bottom = active.rect.y + active.rect.height;
    const minWidth = Math.min(220, maxWidth - 8);
    const minHeight = Math.min(125, maxHeight - 8);
    if (active.direction.includes('w')) left = Math.max(0, Math.min(right - minWidth, left + dx));
    if (active.direction.includes('e')) {
      if (active.docked && dockSide === 'right' && dx > 0) left = Math.max(8, left - dx);
      else right = Math.min(maxWidth - 8, Math.max(left + minWidth, right + dx));
    }
    if (active.direction.includes('n')) top = Math.max(0, Math.min(bottom - minHeight, top + dy));
    if (active.direction.includes('s')) bottom = Math.min(maxHeight - 8, Math.max(top + minHeight, bottom + dy));
    setPosition({ x: left, y: top });
    setSize({ width: right - left, height: bottom - top });
  }
  // The visible dock width is often narrower than the historic floating-panel default.
  // Use the real starting area so dragging a docked panel scales its controls as expected.
  if (placement === 'dock' && dockTarget?.clientWidth) {
    initialArea.current = Math.min(initialArea.current, dockTarget.clientWidth * initial.height);
  }
  const shownWidth = placement === 'dock' && dockTarget?.clientWidth ? dockTarget.clientWidth : size.width;
  const textScale = Math.min(2, Math.max(1, Math.sqrt((shownWidth * size.height) / initialArea.current)));
  const panel = <section ref={frame}
    className={'floating-panel ' + className + (expanded ? ' is-maximized' : '') + (placement === 'dock' ? ' is-docked' : dockSide ? ' is-floating' : '')}
    data-panel-title={title} data-panel-placement={placement} data-dock-side={dockSide ?? ''}
    style={{ left: placement === 'dock' ? undefined : position.x, top: placement === 'dock' ? undefined : position.y,
      width: placement === 'dock' ? undefined : size.width, height: size.height,
      zIndex: layer, order: placement === 'dock' ? dockOrder : undefined,
      '--panel-text-scale': textScale } as React.CSSProperties}
    onPointerDown={() => setLayer(++nextLayer)}>
    <div className="floating-panel-head" onPointerDown={event => {
      if (expanded || event.button !== 0 || (event.target as HTMLElement).closest('button')) return;
      const bounds = frame.current?.getBoundingClientRect();
      drag.current = { x: event.clientX, y: event.clientY,
        left: placement === 'dock' ? bounds?.left ?? 0 : position.x,
        top: placement === 'dock' ? bounds?.top ?? 0 : position.y,
        docked: placement === 'dock', moved: false };
      event.currentTarget.setPointerCapture(event.pointerId);
      event.preventDefault();
    }} onPointerMove={event => {
      const active = drag.current;
      if (!active) return;
      const dx = event.clientX - active.x;
      const dy = event.clientY - active.y;
      if (!active.moved && Math.hypot(dx, dy) < 4) return;
      if (active.docked && !active.moved) {
        const bounds = frame.current?.getBoundingClientRect();
        if (bounds) setSize({ width: bounds.width, height: bounds.height });
        setPlacement('free');
      }
      active.moved = true;
      const parent = frame.current?.parentElement;
      const limitX = dockSide ? window.innerWidth - 110 : (parent?.clientWidth || 0) - 110;
      const limitY = dockSide ? window.innerHeight - 44 : (parent?.clientHeight || 0) - 44;
      setPosition({ x: Math.max(0, Math.min(limitX, active.left + dx)),
        y: Math.max(0, Math.min(limitY, active.top + dy)) });
    }} onPointerUp={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }}>
      <strong>{title}</strong><div className="floating-panel-actions">
        {dockSide && placement === 'free' && <button type="button" onClick={() => setPlacement('dock')}
          aria-label={`将${title}放回${dockSide === 'left' ? '左' : '右'}侧栏`} title="放回侧栏">↩</button>}
        <button type="button" aria-label={(expanded ? '还原' : '选择放大位置') + title}
          aria-expanded={menuOpen} title={expanded ? '还原侧栏' : '选择放大位置'}
          onClick={() => expanded ? restorePanel() : setMenuOpen(open => !open)}>{expanded ? '↙' : '◧'}</button>
        {onClose && <button type="button" onClick={onClose} aria-label={'关闭' + title}>×</button>}
      </div>
      {menuOpen && <div className="panel-placement-menu" role="group" aria-label={`${title}放大位置`}>
        <button type="button" onClick={() => setQuarter('left')}>左侧 ¼ 屏</button>
        <button type="button" onClick={() => setQuarter('right')}>右侧 ¼ 屏</button>
        <button type="button" onClick={() => setQuarter('bottom')}>底部 ¼ 屏</button>
      </div>}
    </div>
    <div className="floating-panel-body">{children}</div>
    {!expanded && ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'].map(direction =>
      <span key={direction} className={'floating-panel-resize resize-' + direction}
        role="separator" aria-label={`从${{ n: '上', ne: '右上', e: '右', se: '右下', s: '下', sw: '左下', w: '左', nw: '左上' }[direction as 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'nw']}调整${title}大小`}
        onPointerDown={event => {
          if (event.button !== 0) return;
          const bounds = frame.current?.getBoundingClientRect();
          resize.current = { direction, x: event.clientX, y: event.clientY,
            rect: placement === 'dock' && bounds ?
              { x: bounds.left, y: bounds.top, width: bounds.width, height: bounds.height } :
              { x: position.x, y: position.y, width: size.width, height: size.height },
            docked: placement === 'dock' };
          event.currentTarget.setPointerCapture(event.pointerId);
          event.preventDefault(); event.stopPropagation();
        }} onPointerMove={resizeMove} onPointerUp={() => { resize.current = null; }}
        onLostPointerCapture={() => { resize.current = null; }} />)}
  </section>;
  return dockTarget ? createPortal(panel, dockTarget) : panel;
}
