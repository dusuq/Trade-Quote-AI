import { Zap } from "lucide-react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center justify-center gap-2">
          <Zap className="h-6 w-6 text-primary" />
          <span className="text-lg font-semibold">TradeQuote AI</span>
        </div>
        {children}
      </div>
    </div>
  );
}
