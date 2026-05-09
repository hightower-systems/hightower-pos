import { type ReactNode, useEffect, useRef, useState } from "react";

interface Props {
  left: ReactNode;
  right: ReactNode;
  storageKey: string;
  defaultRightWidth?: number;
  minLeftWidth?: number;
  minRightWidth?: number;
  maxRightWidth?: number;
}

function readStoredWidth(key: string, fallback: number): number {
  if (typeof window === "undefined") return fallback;
  const raw = window.localStorage.getItem(key);
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function SplitPane({
  left,
  right,
  storageKey,
  defaultRightWidth = 360,
  minLeftWidth = 480,
  minRightWidth = 240,
  maxRightWidth = 800,
}: Props) {
  const [rightWidth, setRightWidth] = useState(() =>
    readStoredWidth(storageKey, defaultRightWidth),
  );
  const dragging = useRef(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onMove(event: MouseEvent) {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const proposed = rect.right - event.clientX;
      const maxByLeft = rect.width - minLeftWidth;
      const clamped = Math.max(
        minRightWidth,
        Math.min(maxRightWidth, Math.min(proposed, maxByLeft)),
      );
      setRightWidth(clamped);
    }
    function onUp() {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      try {
        window.localStorage.setItem(storageKey, String(rightWidth));
      } catch {
        // localStorage may be unavailable; the in-memory width still works
      }
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [rightWidth, storageKey, minLeftWidth, minRightWidth, maxRightWidth]);

  function handleDragStart() {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  return (
    <div ref={containerRef} className="flex w-full flex-1 overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col">{left}</div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize cart and bookmarks panes"
        onMouseDown={handleDragStart}
        className="group relative w-1.5 shrink-0 cursor-col-resize bg-surface-border hover:bg-brand-red/40"
      >
        <div className="absolute inset-y-0 -left-1 -right-1" />
      </div>
      <div
        style={{ width: rightWidth }}
        className="flex shrink-0 flex-col bg-surface-card"
        data-testid="split-right-pane"
      >
        {right}
      </div>
    </div>
  );
}
