"use client";

import * as React from "react";
import { Sparkles, ShieldCheck, ListOrdered, BookOpen, User, Key, Lock, Check } from "lucide-react";
import { CaptureBox } from "@/components/capture-box";
import { TodayView } from "@/components/today-view";
import { ApprovalReview } from "@/components/approval-review";
import { TaskDirectory } from "@/components/task-directory";
import { SkillsLibrary } from "@/components/skills-library";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { clientAdapter } from "@/lib/api";

type TabValue = "today" | "approvals" | "directory" | "skills";

/**
 * Operational dashboard page module.
 * Composes the primary execution workflows into a calm, focused workspace interface.
 * Maintains strict code locality while leveraging the underlying client adapter seam.
 */
export default function HomePage() {
  const [ownerId, setOwnerId] = React.useState("default_user");
  const [refreshTrigger, setRefreshTrigger] = React.useState(0);
  const [isEditingOwner, setIsEditingOwner] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState<TabValue>("today");

  // Focus ref for fast capture navigation
  const captureInputRef = React.useRef<HTMLInputElement | null>(null);

  // Authentication configuration modal
  const [isAuthOpen, setIsAuthOpen] = React.useState(false);
  const [tokenInput, setTokenInput] = React.useState("");
  const [hasActiveToken, setHasActiveToken] = React.useState(false);

  React.useEffect(() => {
    const existing = clientAdapter.getAuthToken();
    if (existing) {
      setHasActiveToken(true);
      setTokenInput(existing);
    }
  }, []);

  // Global keyboard navigation with strict input editing guards
  React.useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const isEditing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        Boolean(target?.isContentEditable);

      // Cmd+K or Ctrl+K focuses capture input unconditionally
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        captureInputRef.current?.focus();
        return;
      }

      // / focuses capture input only when not actively editing
      if (e.key === "/" && !isEditing) {
        e.preventDefault();
        captureInputRef.current?.focus();
        return;
      }

      // Tab switcher shortcuts 1, 2, 3, 4 only outside editable elements
      if (!isEditing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        if (e.key === "1") {
          setActiveTab("today");
        } else if (e.key === "2") {
          setActiveTab("approvals");
        } else if (e.key === "3") {
          setActiveTab("directory");
        } else if (e.key === "4") {
          setActiveTab("skills");
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const triggerRefresh = React.useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
  }, []);

  function handleSaveToken(e: React.FormEvent) {
    e.preventDefault();
    clientAdapter.setAuthToken(tokenInput.trim() || null);
    setHasActiveToken(Boolean(tokenInput.trim()));
    setIsAuthOpen(false);
    triggerRefresh();
  }

  function handleClearToken() {
    clientAdapter.setAuthToken(null);
    setTokenInput("");
    setHasActiveToken(false);
    setIsAuthOpen(false);
    triggerRefresh();
  }

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
                M6 Agent Runtime Active
              </span>
            </div>
            <p className="text-xs text-cream-muted">
              Execution partner — turn commitments into completed, verified work.
            </p>
          </div>

          {/* Tenant Identity & Access Controls */}
          <div className="flex items-center gap-2.5 self-start sm:self-auto">
            {/* Bearer Token Trigger */}
            <button
              type="button"
              onClick={() => setIsAuthOpen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-surface-cork/80 bg-[#160d07] hover:border-surface-cork text-cream-muted hover:text-cream text-[11px] font-mono transition-colors"
              title="Configure authentication bearer token"
            >
              <Key className={`h-3 w-3 ${hasActiveToken ? "text-emerald-400" : "text-cream-muted"}`} />
              <span>{hasActiveToken ? "Token Active" : "No Auth"}</span>
            </button>

            {/* Owner Identity Badge */}
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
                title="Click to edit tenant owner identity"
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
          <CaptureBox
            ownerId={ownerId}
            onCaptured={triggerRefresh}
            inputRef={captureInputRef}
          />
        </section>

        {/* Tabbed Execution Center */}
        <section>
          <Tabs
            value={activeTab}
            onValueChange={(val) => setActiveTab(val as TabValue)}
            className="w-full"
          >
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
              <TabsTrigger value="skills" className="flex items-center gap-1.5">
                <BookOpen className="h-3.5 w-3.5" />
                <span>Skills Library</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="today" className="pt-2">
              <TodayView
                ownerId={ownerId}
                refreshTrigger={refreshTrigger}
                onRefreshNeeded={triggerRefresh}
                onNavigateToApprovals={() => setActiveTab("approvals")}
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

            <TabsContent value="skills" className="pt-2">
              <SkillsLibrary
                ownerId={ownerId}
                onRefresh={triggerRefresh}
              />
            </TabsContent>
          </Tabs>
        </section>
      </div>

      {/* Authentication & Access Token Dialog */}
      <Dialog open={isAuthOpen} onOpenChange={setIsAuthOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="flex items-center gap-2 text-ember">
              <Lock className="h-4 w-4" />
              <DialogTitle>Authentication & Tenant Security</DialogTitle>
            </div>
            <DialogDescription className="text-xs text-cream-muted">
              When authentication is configured on the backend via PRAXIS_AUTH_TOKENS, requests require a valid Bearer token matching the claimed tenant owner.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSaveToken} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-[10px] uppercase font-mono tracking-wider text-cream-muted block">
                Bearer Access Token:
              </label>
              <Input
                type="password"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Enter secret bearer token..."
                className="bg-[#100904] border-surface-cork text-xs font-mono"
                autoFocus
              />
            </div>

            <div className="p-3 rounded-lg bg-[#140c06] border border-surface-cork/50 text-[11px] text-cream-muted space-y-1">
              <span className="text-[10px] font-bold uppercase text-cream block">
                Current Tenant Scope:
              </span>
              <p className="font-mono text-cream/90">{ownerId}</p>
              <p className="text-[10px] text-cream-muted/70 pt-1">
                Note: In local mode without authentication tokens configured, any tenant identifier is accepted.
              </p>
            </div>

            <DialogFooter className="gap-2 sm:gap-0">
              {hasActiveToken && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleClearToken}
                  className="border-red-900/60 text-red-300 hover:bg-red-950/40"
                >
                  Clear Token
                </Button>
              )}
              <Button
                type="submit"
                size="sm"
                className="bg-surface-bark text-cream border border-surface-cork hover:bg-[#4a301e]"
              >
                <Check className="h-3 w-3 mr-1" />
                Save & Apply
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Editorial Micro Footer with Shortcuts HUD */}
      <footer className="border-t border-surface-cork/40 border-dashed py-8 mt-16 text-center text-[10px] text-cream-muted uppercase tracking-widest space-y-3">
        <div className="flex flex-wrap items-center justify-center gap-3 text-cream-muted/80 font-mono text-[10px] normal-case">
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded bg-surface-card border border-surface-cork text-cream font-mono">/</kbd> Focus Capture
          </span>
          <span className="text-surface-cork">·</span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded bg-surface-card border border-surface-cork text-cream font-mono">1</kbd> Today
          </span>
          <span className="text-surface-cork">·</span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded bg-surface-card border border-surface-cork text-cream font-mono">2</kbd> Approvals
          </span>
          <span className="text-surface-cork">·</span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded bg-surface-card border border-surface-cork text-cream font-mono">3</kbd> Commitments
          </span>
        </div>
        <p>Praxis Execution System · Bounded Autonomy & Evidence Verification</p>
      </footer>
    </main>
  );
}
