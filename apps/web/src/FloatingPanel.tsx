import { useRef, useState, type ReactNode } from 'react';

let nextLayer = 20;
type Rect = { x: number; y: number; width: number; height: number };

export function FloatingPanel({ title, initial, children, onClose, className = '', halfSide = 'right' }: {
  title: string; initial: Rect; children: ReactNode; onClose?: () => void;
  className?: string; halfSide?: 'left' | 'right';
}) {
  const [position, setPosition] = useState({ x: initial.x, y: initial.y });
  const [size, setSize] = useState({ width: initial.width, height: initial.height });
  const [maximized, setMaximized] = useState(false);
  const [layer, setLayer] = useState(++nextLayer);
  const initialArea = useRef(Math.max(1, initial.width * initial.height));
  const restore = useRef<Rect | null>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const resize = useRef<{ direction: string; x: number; y: number; rect: Rect } | null>(null);
  const frame = useRef<HTMLElement | null>(null);
  function resizeMove(event: React.PointerEvent<HTMLSpanElement>) {
    const active = resize.current;
    const parent = frame.current?.parentElement;
    if (!active || !parent) return;
    const dx = event.clientX - active.x;
    const dy = event.clientY - active.y;
    const minWidth = Math.min(220, parent.clientWidth - 8);
    const minHeight = Math.min(125, parent.clientHeight - 8);
    let left = active.rect.x;
    let top = active.rect.y;
    let right = active.rect.x + active.rect.width;
    let bottom = active.rect.y + active.rect.height;
    if (active.direction.includes('w')) left = Math.max(0, Math.min(right - minWidth, left + dx));
    if (active.direction.includes('e')) right = Math.min(parent.clientWidth - 8, Math.max(left + minWidth, right + dx));
    if (active.direction.includes('n')) top = Math.max(0, Math.min(bottom - minHeight, top + dy));
    if (active.direction.includes('s')) bottom = Math.min(parent.clientHeight - 8, Math.max(top + minHeight, bottom + dy));
    setPosition({ x: left, y: top });
    setSize({ width: right - left, height: bottom - top });
  }
  function toggleHalfScreen() {
    if (maximized) {
      const old = restore.current;
      if (old) { setPosition({ x: old.x, y: old.y }); setSize({ width: old.width, height: old.height }); }
      setMaximized(false);
      return;
    }
    const parent = frame.current?.parentElement;
    const element = frame.current;
    if (!parent || !element) return;
    const bounds = element.getBoundingClientRect();
    restore.current = { x: position.x, y: position.y, width: bounds.width, height: bounds.height };
    const half = Math.max(160, Math.floor(parent.clientWidth / 2) - 8);
    setSize({ width: half, height: Math.max(125, parent.clientHeight - 16) });
    setPosition({ x: halfSide === 'left' ? 8 : parent.clientWidth - half - 8, y: 8 });
    setMaximized(true);
  }
  const textScale = Math.min(2, Math.max(1,
    Math.sqrt((size.width * size.height) / initialArea.current)));
  return <section ref={frame} className={'floating-panel ' + className + (maximized ? ' is-maximized' : '')}
    style={{ left: position.x, top: position.y, width: size.width, height: size.height, zIndex: layer,
      '--panel-text-scale': textScale } as React.CSSProperties}
    onPointerDown={() => setLayer(++nextLayer)}>
    <div className="floating-panel-head" onPointerDown={event => {
      if (maximized || event.button !== 0 || (event.target as HTMLElement).closest('button')) return;
      drag.current = { x: event.clientX, y: event.clientY, left: position.x, top: position.y };
      event.currentTarget.setPointerCapture(event.pointerId);
      event.preventDefault();
    }} onPointerMove={event => {
      if (!drag.current) return;
      const parent = frame.current?.parentElement;
      const bounds = frame.current?.getBoundingClientRect();
      const limitX = Math.max(0, (parent?.clientWidth || 0) - Math.min(110, bounds?.width || 110));
      const limitY = Math.max(0, (parent?.clientHeight || 0) - 44);
      setPosition({ x: Math.max(0, Math.min(limitX, drag.current.left + event.clientX - drag.current.x)),
        y: Math.max(0, Math.min(limitY, drag.current.top + event.clientY - drag.current.y)) });
    }} onPointerUp={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }}>
      <strong>{title}</strong><div className="floating-panel-actions">
        <button type="button" onClick={toggleHalfScreen} aria-label={(maximized ? '还原' : '半屏放大') + title}
          title={maximized ? '还原窗口' : '放大到半屏'}>{maximized ? '↙' : '◧'}</button>
        {onClose && <button type="button" onClick={onClose} aria-label={'关闭' + title}>×</button>}
      </div>
    </div>
    <div className="floating-panel-body">{children}</div>
    {!maximized && ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'].map(direction =>
      <span key={direction} className={'floating-panel-resize resize-' + direction}
        role="separator" aria-label={`从${{ n: '上', ne: '右上', e: '右', se: '右下', s: '下', sw: '左下', w: '左', nw: '左上' }[direction as 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'nw']}调整${title}大小`}
        onPointerDown={event => {
          if (event.button !== 0) return;
          resize.current = { direction, x: event.clientX, y: event.clientY,
            rect: { x: position.x, y: position.y, width: size.width, height: size.height } };
          event.currentTarget.setPointerCapture(event.pointerId);
          event.preventDefault(); event.stopPropagation();
        }} onPointerMove={resizeMove} onPointerUp={() => { resize.current = null; }}
        onLostPointerCapture={() => { resize.current = null; }} />)}
  </section>;
}
