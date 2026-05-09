import { describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@testing-library/react";

import { useKeyboardShortcuts } from "../src/hooks/useKeyboardShortcuts";

function Probe({ shortcuts }: { shortcuts: Parameters<typeof useKeyboardShortcuts>[0] }) {
  useKeyboardShortcuts(shortcuts);
  return <div data-testid="probe" />;
}

describe("useKeyboardShortcuts", () => {
  it("fires the matched handler when its key is pressed", () => {
    const handler = vi.fn();
    render(<Probe shortcuts={[{ key: "F2", handler }]} />);
    fireEvent.keyDown(document, { key: "F2" });
    expect(handler).toHaveBeenCalledOnce();
  });

  it("does not fire when enabled is false", () => {
    const handler = vi.fn();
    render(<Probe shortcuts={[{ key: "F2", handler, enabled: false }]} />);
    fireEvent.keyDown(document, { key: "F2" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("matches keys case-insensitively (F2 matches f2)", () => {
    const handler = vi.fn();
    render(<Probe shortcuts={[{ key: "F2", handler }]} />);
    fireEvent.keyDown(document, { key: "f2" });
    expect(handler).toHaveBeenCalledOnce();
  });

  it("ignores keys that don't match any shortcut", () => {
    const handler = vi.fn();
    render(<Probe shortcuts={[{ key: "F2", handler }]} />);
    fireEvent.keyDown(document, { key: "F1" });
    fireEvent.keyDown(document, { key: "Enter" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("dispatches to the first match when multiple shortcuts are registered", () => {
    const cash = vi.fn();
    const card = vi.fn();
    render(
      <Probe
        shortcuts={[
          { key: "F1", handler: cash },
          { key: "F2", handler: card },
        ]}
      />,
    );
    fireEvent.keyDown(document, { key: "F1" });
    fireEvent.keyDown(document, { key: "F2" });
    expect(cash).toHaveBeenCalledOnce();
    expect(card).toHaveBeenCalledOnce();
  });

  it("removes the listener on unmount", () => {
    const handler = vi.fn();
    const { unmount } = render(<Probe shortcuts={[{ key: "F2", handler }]} />);
    unmount();
    fireEvent.keyDown(document, { key: "F2" });
    expect(handler).not.toHaveBeenCalled();
  });
});
