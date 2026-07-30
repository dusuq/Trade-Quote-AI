import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { QuoteDraft } from "@/lib/ai";

interface AiDraftBannerProps {
  draft: QuoteDraft;
}

/**
 * Shown once, immediately after an AI-drafted quote is created — reads the
 * extraction result the create call returned (M15 web UI spec §4.2). Nothing
 * has been sent to the customer yet; this is purely a review aid.
 */
export function AiDraftBanner({ draft }: AiDraftBannerProps) {
  return (
    <Card className="border-primary/40 bg-primary/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          AI-drafted quote
          <Badge variant="secondary" className="capitalize">
            {draft.trade}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-muted-foreground">Review before sending — nothing has been sent yet.</p>
        <p>{draft.summary}</p>
        {draft.notes && <p className="text-muted-foreground">{draft.notes}</p>}
        {draft.transcript && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">Transcript: </span>
            {draft.transcript}
          </p>
        )}
        {draft.unmatched_count > 0 && (
          <p className="font-medium text-destructive">
            {draft.unmatched_count} line{draft.unmatched_count === 1 ? "" : "s"} need pricing —
            flagged below.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
