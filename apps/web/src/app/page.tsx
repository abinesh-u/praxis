"use client";

import * as React from "react";
import { Sparkles, ShieldCheck, ListOrdered, User } from "lucide-react";
import { CaptureBox } from "@/components/capture-box";
import { TodayView } from "@/components/today-view";
import { ApprovalReview } from "@/components/approval-review";
import { TaskDirectory } from "@/components/task-directory";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";

/**
 * Operational dashboard page module.
 * Composes the primary execution workflows into a calm, focused workspace interface.
 * Maintains strict code locality while leveraging the underlying client adapter seam.
 */
export default function HomePage() {
  const [ownerId, setOwnerId] = React.useState("default_user");
  const [refreshTrigger, setRefreshTrigger] = React.useState(0);
  const [isEditingOwner, setIsEditingOwner] = React.useState(false);

  const triggerRefresh = React.useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
  }, []);

  return (
    <main className="min-h-screen bg-[#100904] text-cream">
      {/* Top Editorial Header */}
      <header className="border-b border-surface-cork border-dashed px-6 py-5">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-0.5">
            <div className="flex items-center gap-2.5">
              <span className="text-sm font-semibold tracking-widest uppercase text-cream">
                Praxis
              </span>
              <span className="text-[10px] uppercase tracking-wider text-ember bg-surface-bark/60 border border-surface-cork px-2 py-0.5 rounded-full font-mono">
                M4 Operational
              </span>
            </div>
            <p className="text-xs text-cream-muted">
              Execution partner — turn commitments into completed, verified work.
            </p>
          </div>

          {/* Owner Identity Badge */}
          <div className="flex items-center gap-2 self-start sm:self-auto">
            {isEditingOwner ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setIsEditingOwner(false);
                  triggerRefresh();
                }}
                className="flex items-center gap-1.5"
              >
                <Input
                  value={ownerId}
                  onChange={(e) => setOwnerId(e.target.value)}
                  className="h-7 w-32 text-[11px] bg-[#1a110a] border-surface-cork font-mono"
                  autoFocus
                  onBlur={() => {
                    setIsEditingOwner(false);
                    triggerRefresh();
                  }}
                />
              </form>
            ) : (
              <button
                type="button"
                onClick={() => setIsEditingOwner(true)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-surface-cork/80 bg-[#160d07] hover:border-surface-cork text-cream-muted hover:text-cream text-[11px] font-mono transition-colors"
                title="Click to change owner identity"
              >
                <User className="h-3 w-3 text-ember" />
                <span>{ownerId}</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Workspace Body */}
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
        {/* Natural Language Capture Seam */}
        <section className="space-y-2">
          <CaptureBox ownerId={ownerId} onCaptured={triggerRefresh} />
        </section>

        {/* Tabbed Execution Center */}
        <section>
          <Tabs defaultValue="today" className="w-full">
            <TabsList>
              <TabsTrigger value="today" className="flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5" />
                <span>Today</span>
              </TabsTrigger>
              <TabsTrigger value="approvals" className="flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5" />
                <span>Approvals</span>
              </TabsTrigger>
              <TabsTrigger value="directory" className="flex items-center gap-1.5">
                <ListOrdered className="h-3.5 w-3.5" />
                <span>All Commitments</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="today" className="pt-2">
              <TodayView
                ownerId={ownerId}
                refreshTrigger={refreshTrigger}
                onRefreshNeeded={triggerRefresh}
              />
            </TabsContent>

            <TabsContent value="approvals" className="pt-2">
              <ApprovalReview
                ownerId={ownerId}
                onDecision={triggerRefresh}
              />
            </TabsContent>

            <TabsContent value="directory" className="pt-2">
              <TaskDirectory
                ownerId={ownerId}
                refreshTrigger={refreshTrigger}
                onRefreshNeeded={triggerRefresh}
              />
            </TabsContent>
          </Tabs>
        </section>
      </div>

      {/* Editorial Micro Footer */}
      <footer className="border-t border-surface-cork/40 border-dashed py-8 mt-16 text-center text-[10px] text-cream-muted uppercase tracking-widest">
        <span>Praxis Execution System · Bounded Autonomy & Evidence Verification</span>
      </footer>
    </main>
  );
}
