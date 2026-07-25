import * as React from "react";
import Link from "next/link";
import { Zap } from "lucide-react";
import { SidebarNav } from "@/components/app-shell/nav";
import { buttonVariants } from "@/components/ui/button";

/** The authenticated app shell: fixed sidebar + top bar + content area. */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="hidden w-60 shrink-0 border-r bg-card md:flex md:flex-col">
        <div className="flex h-14 items-center gap-2 border-b px-5">
          <Zap className="h-5 w-5 text-primary" />
          <span className="font-semibold">TradeQuote AI</span>
        </div>
        <SidebarNav />
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b bg-background px-6">
          <div className="flex items-center gap-2 md:hidden">
            <Zap className="h-5 w-5 text-primary" />
            <span className="font-semibold">TradeQuote AI</span>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <Link href="/quotes/new" className={buttonVariants({ variant: "default", size: "sm" })}>
              New Quote
            </Link>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
