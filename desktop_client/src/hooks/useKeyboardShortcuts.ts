import { useEffect } from "react";

export interface ShortcutBinding {
  key: string;
  handler: () => void;
  enabled?: boolean;
}

export function useKeyboardShortcuts(shortcuts: ShortcutBinding[]): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      for (const shortcut of shortcuts) {
        if (shortcut.enabled === false) continue;
        if (shortcut.key.toLowerCase() !== event.key.toLowerCase()) continue;
        event.preventDefault();
        shortcut.handler();
        return;
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [shortcuts]);
}
