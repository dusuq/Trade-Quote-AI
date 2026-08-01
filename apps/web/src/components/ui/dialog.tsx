"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}

/** Elements that can hold focus, in DOM order. `:not([disabled])` matters —
 * a disabled submit button must not be a tab stop. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Lightweight, dependency-free modal — this app's first true overlay
 * component (every prior "dialog"-shaped feature here is an inline panel).
 * Closes on Escape or backdrop click.
 *
 * Traps focus and restores it to the trigger on close (T204c). Without the
 * trap, `aria-modal="true"` was a lie: it tells assistive technology that
 * everything outside is inert, while Tab still walked onto the page behind.
 */
export function Dialog({ open, onClose, title, children, className }: DialogProps) {
  const panelRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;

    // Remember what to hand focus back to, before we move it.
    const previouslyFocused = document.activeElement as HTMLElement | null;

    function focusable(): HTMLElement[] {
      return Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    }

    // Focus the panel itself rather than the first focusable control. The
    // first control in DOM order is the close (X) button, so focusing it would
    // mean a keyboard user's first Enter dismisses the dialog. Focusing the
    // container is the WAI-ARIA APG pattern and Tab then proceeds naturally.
    panelRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      // Re-query every time: the focusable set changes as fields are filled
      // and the submit button enables.
      const items = focusable();
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && (active === first || !panelRef.current?.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className={cn(
          "max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border bg-card p-6 text-card-foreground shadow-lg",
          className,
        )}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button
            type="button"
            aria-label="Close"
            className="text-muted-foreground hover:text-foreground"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
