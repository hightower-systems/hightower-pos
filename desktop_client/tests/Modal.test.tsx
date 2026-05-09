import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { Modal } from "../src/components/Modal";

describe("<Modal>", () => {
  it("returns null when closed", () => {
    const { container } = render(
      <Modal open={false} onClose={() => {}} title="Demo">
        <p>hidden body</p>
      </Modal>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the title and body when open", () => {
    render(
      <Modal open={true} onClose={() => {}} title="Pick warehouse">
        <p>visible body</p>
      </Modal>,
    );
    expect(
      screen.getByRole("dialog", { name: /pick warehouse/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("visible body")).toBeInTheDocument();
  });

  it("calls onClose when the Close button is clicked", async () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Demo">
        <p>body</p>
      </Modal>,
    );
    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when Escape is pressed", async () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Demo">
        <p>body</p>
      </Modal>,
    );
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when the backdrop is clicked", async () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Demo">
        <p>body</p>
      </Modal>,
    );
    await userEvent.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does not call onClose when clicking inside the modal body", async () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Demo">
        <p>body text</p>
      </Modal>,
    );
    await userEvent.click(screen.getByText("body text"));
    expect(onClose).not.toHaveBeenCalled();
  });
});
