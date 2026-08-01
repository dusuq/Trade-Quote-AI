// @vitest-environment jsdom
/**
 * Focus-management tests for Dialog (T204d, covering what T204c shipped).
 *
 * `aria-modal="true"` tells assistive technology that everything outside the
 * dialog is inert. That's only true if focus actually can't leave, so these
 * assert the trap rather than the attribute.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Dialog } from "@/components/ui/dialog";

afterEach(() => {
  cleanup();
});

function renderDialog(onClose = vi.fn()) {
  const result = render(
    <Dialog open onClose={onClose} title="Request E-Signature">
      <input aria-label="Signer name" />
      <input aria-label="Signer email" />
      <button type="button">Send</button>
      <button type="button" disabled>
        Disabled action
      </button>
    </Dialog>,
  );
  return { ...result, onClose };
}

describe("Dialog focus management", () => {
  it("moves focus onto the dialog itself on open", () => {
    renderDialog();
    // The panel, not the first control — the first control in DOM order is the
    // close button, so focusing it would make the user's first Enter dismiss
    // the dialog. Without moving focus at all, they'd stay on the trigger
    // behind the overlay.
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
  });

  it("wraps Tab from the last focusable back to the first", () => {
    renderDialog();
    const send = screen.getByRole("button", { name: "Send" });
    send.focus();

    fireEvent.keyDown(document, { key: "Tab" });

    // The close (X) button is first in DOM order.
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close" }));
  });

  it("wraps Shift+Tab from the first focusable back to the last", () => {
    renderDialog();
    const close = screen.getByRole("button", { name: "Close" });
    close.focus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Send" }));
  });

  it("does not treat a disabled button as a tab stop", () => {
    renderDialog();
    const send = screen.getByRole("button", { name: "Send" });
    send.focus();

    fireEvent.keyDown(document, { key: "Tab" });

    // If :not([disabled]) were missing, focus would land on "Disabled action"
    // and the user would appear stuck.
    expect(document.activeElement).not.toBe(
      screen.getByRole("button", { name: "Disabled action" }),
    );
  });

  it("pulls focus back when it has escaped the panel", () => {
    renderDialog();
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    outside.focus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Send" }));
    outside.remove();
  });

  it("restores focus to the trigger when it closes", () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();

    const { unmount } = renderDialog();
    expect(document.activeElement).not.toBe(trigger);

    unmount();

    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });

  it("closes on Escape", () => {
    const { onClose } = renderDialog();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
