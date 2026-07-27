"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { listTemplates, type ProposalTemplate } from "@/lib/proposal-templates";
import { TemplateForm } from "@/components/settings/template-form";

interface TemplateManagerProps {
  token: string;
}

export function TemplateManager({ token }: TemplateManagerProps) {
  const [formOpen, setFormOpen] = React.useState(false);
  const [editingTemplate, setEditingTemplate] = React.useState<ProposalTemplate | undefined>(undefined);

  const {
    data: templates,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["proposal-templates"],
    queryFn: () => listTemplates(token),
    enabled: !!token,
  });

  function openCreate() {
    setEditingTemplate(undefined);
    setFormOpen(true);
  }

  function openEdit(template: ProposalTemplate) {
    setEditingTemplate(template);
    setFormOpen(true);
  }

  function closeForm() {
    setFormOpen(false);
    setEditingTemplate(undefined);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle>Proposal Templates</CardTitle>
        {!formOpen && templates && templates.length > 0 && (
          <Button size="sm" onClick={openCreate}>
            New Template
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {formOpen && (
          <TemplateForm token={token} template={editingTemplate} onSaved={closeForm} onCancel={closeForm} />
        )}

        {!formOpen && (
          <>
            {isLoading && <p className="text-sm text-muted-foreground">Loading templates…</p>}
            {isError && (
              <div className="space-y-2">
                <p className="text-sm text-destructive">
                  Couldn&apos;t load proposal templates. Is the API Gateway running?
                </p>
                <Button size="sm" variant="outline" onClick={() => refetch()}>
                  Retry
                </Button>
              </div>
            )}
            {templates && templates.length === 0 && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  No proposal templates yet. Create one to start sending branded proposals.
                </p>
                <Button size="sm" onClick={openCreate}>
                  Create your first template
                </Button>
              </div>
            )}
            {templates && templates.length > 0 && (
              <div className="divide-y">
                {templates.map((template) => (
                  <div key={template.id} className="flex items-center justify-between py-3">
                    <div className="flex items-center gap-3">
                      <span
                        className="h-4 w-4 shrink-0 rounded-full border"
                        style={{ backgroundColor: template.primary_color }}
                        aria-hidden
                      />
                      <div>
                        <p className="text-sm font-medium">
                          {template.name}{" "}
                          {template.is_default && (
                            <Badge variant="secondary" className="ml-1 align-middle">
                              Default
                            </Badge>
                          )}
                        </p>
                        <p className="text-sm text-muted-foreground">{template.company_name}</p>
                      </div>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => openEdit(template)}>
                      Edit
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
