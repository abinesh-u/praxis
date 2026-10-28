"use client";

import * as React from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Sparkles,
  Check,
  X,
  ChevronDown,
  ChevronUp,
  Loader2,
  AlertTriangle,
  FileCode,
  Terminal,
  Hash,
  Clock,
  RefreshCw,
  Info,
} from "lucide-react";
import {
  clientAdapter,
  type SkillResponse,
  type SkillStatus,
  AuthenticationError,
  ForbiddenError,
  TransportError,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface SkillsLibraryProps {
  ownerId: string;
  onRefresh?: () => void;
}

type LibrarySubTab = "candidates" | "active" | "archived";

export function SkillsLibrary({ ownerId, onRefresh }: SkillsLibraryProps) {
  const [activeSubTab, setActiveSubTab] = React.useState<LibrarySubTab>("candidates");
  const [skills, setSkills] = React.useState<SkillResponse[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // Expanded instructions state: set of skill names
  const [expandedInstructions, setExpandedInstructions] = React.useState<Record<string, boolean>>({});

  // Promotion modal state
  const [promoteCandidate, setPromoteCandidate] = React.useState<SkillResponse | null>(null);
  const [promotionNotes, setPromotionNotes] = React.useState("");
  const [isPromoting, setIsPromoting] = React.useState(false);
  const [promotionError, setPromotionError] = React.useState<string | null>(null);

  // Rejection modal state
  const [rejectCandidate, setRejectCandidate] = React.useState<SkillResponse | null>(null);
  const [rejectionReason, setRejectionReason] = React.useState("");
  const [isRejecting, setIsRejecting] = React.useState(false);
  const [rejectionError, setRejectionError] = React.useState<string | null>(null);

  const fetchSkills = React.useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const response = await clientAdapter.listSkills(undefined, ownerId);
      setSkills(response.skills);
    } catch (err) {
      if (err instanceof AuthenticationError) {
        setErrorMessage("Authentication required or token expired. Please configure a valid Bearer token in settings.");
      } else if (err instanceof ForbiddenError) {
        setErrorMessage("Access forbidden. Your authenticated identity cannot access this tenant's skills.");
      } else if (err instanceof TransportError) {
        setErrorMessage(err.message || `Failed to fetch skills (HTTP ${err.status})`);
      } else {
        setErrorMessage("Network error: unable to load procedural skills from server.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [ownerId]);

  React.useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const toggleExpand = (skillName: string) => {
    setExpandedInstructions((prev) => ({
      ...prev,
      [skillName]: !prev[skillName],
    }));
  };

  const handleOpenPromote = (skill: SkillResponse) => {
    setPromoteCandidate(skill);
    setPromotionNotes("");
    setPromotionError(null);
  };

  const handleConfirmPromote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promoteCandidate) return;

    setIsPromoting(true);
    setPromotionError(null);
    try {
      const updated = await clientAdapter.promoteSkill({
        skillName: promoteCandidate.name,
        notes: promotionNotes.trim() || undefined,
      });

      // Update state strictly after backend confirmation
      setSkills((prev) =>
        prev.map((s) => (s.name === updated.name ? updated : s))
      );
      setPromoteCandidate(null);
      onRefresh?.();
    } catch (err) {
      if (err instanceof TransportError) {
        setPromotionError(err.message || `Promotion failed (HTTP ${err.status})`);
      } else if (err instanceof AuthenticationError) {
        setPromotionError("Authentication expired. Please re-authenticate.");
      } else if (err instanceof ForbiddenError) {
        setPromotionError("Unauthorized: you do not have permission to promote this candidate.");
      } else {
        setPromotionError("Failed to promote candidate due to a network error.");
      }
    } finally {
      setIsPromoting(false);
    }
  };

  const handleOpenReject = (skill: SkillResponse) => {
    setRejectCandidate(skill);
    setRejectionReason("");
    setRejectionError(null);
  };

  const handleConfirmReject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectCandidate) return;

    if (!rejectionReason.trim()) {
      setRejectionError("A review reason is mandatory to reject a candidate.");
      return;
    }

    setIsRejecting(true);
    setRejectionError(null);
    try {
      const updated = await clientAdapter.rejectSkill({
        skillName: rejectCandidate.name,
        reason: rejectionReason.trim(),
      });

      // Update state strictly after backend confirmation
      setSkills((prev) =>
        prev.map((s) => (s.name === updated.name ? updated : s))
      );
      setRejectCandidate(null);
      onRefresh?.();
    } catch (err) {
      if (err instanceof TransportError) {
        setRejectionError(err.message || `Rejection failed (HTTP ${err.status})`);
      } else if (err instanceof AuthenticationError) {
        setRejectionError("Authentication expired. Please re-authenticate.");
      } else if (err instanceof ForbiddenError) {
        setRejectionError("Unauthorized: you do not have permission to reject this candidate.");
      } else {
        setRejectionError("Failed to reject candidate due to a network error.");
      }
    } finally {
      setIsRejecting(false);
    }
  };

  // Group skills by status
  const candidates = skills.filter((s) => s.status === "candidate");
  const validatedSkills = skills.filter((s) => s.status === "validated");
  const rejectedSkills = skills.filter((s) => s.status === "rejected");

  return (
    <div className="space-y-6">
      {/* Editorial Header Section */}
      <div className="border border-surface-cork/40 bg-walnut-surface/30 p-6 rounded-xl relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] uppercase font-mono tracking-widest text-ember font-semibold">
                Milestone M8 — Procedural Knowledge
              </span>
              <span className="text-surface-cork">•</span>
              <span className="text-[10px] uppercase font-mono tracking-wider text-muted-cream">
                Validation Seam
              </span>
            </div>
            <h2 className="text-xl font-medium tracking-tight text-cream">Skills Library & Operator Review</h2>
            <p className="text-sm text-muted-cream mt-0.5">
              Inspect distilled procedural workflows, review provenance receipts, and promote verified skills into active execution depth.
            </p>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={fetchSkills}
            disabled={isLoading}
            className="self-start md:self-auto border border-surface-cork/60 hover:border-cream/40 text-cream text-xs uppercase tracking-wider"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {/* Sub-navigation tabs with count indicators */}
        <div className="mt-6 pt-4 border-t border-surface-cork/30">
          <Tabs value={activeSubTab} onValueChange={(val) => setActiveSubTab(val as LibrarySubTab)}>
            <TabsList className="bg-transparent border border-surface-cork/50 p-1 rounded-full inline-flex gap-1">
              <TabsTrigger
                value="candidates"
                className="rounded-full text-xs font-mono uppercase tracking-wider px-4 py-1.5 data-[state=active]:bg-surface-bark data-[state=active]:text-cream transition-all"
              >
                Candidates
                <span className={`ml-2 px-1.5 py-0.2 rounded-full text-[10px] ${
                  candidates.length > 0 ? "bg-ember text-cream" : "bg-surface-cork text-muted-cream"
                }`}>
                  {candidates.length}
                </span>
              </TabsTrigger>

              <TabsTrigger
                value="active"
                className="rounded-full text-xs font-mono uppercase tracking-wider px-4 py-1.5 data-[state=active]:bg-surface-bark data-[state=active]:text-cream transition-all"
              >
                Active Library
                <span className="ml-2 px-1.5 py-0.2 rounded-full text-[10px] bg-surface-cork text-muted-cream">
                  {validatedSkills.length}
                </span>
              </TabsTrigger>

              <TabsTrigger
                value="archived"
                className="rounded-full text-xs font-mono uppercase tracking-wider px-4 py-1.5 data-[state=active]:bg-surface-bark data-[state=active]:text-cream transition-all"
              >
                Archived
                <span className="ml-2 px-1.5 py-0.2 rounded-full text-[10px] bg-surface-cork text-muted-cream">
                  {rejectedSkills.length}
                </span>
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {/* Error Banner */}
      {errorMessage && (
        <div className="border border-ember/40 bg-ember/10 p-4 rounded-xl flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-ember shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h4 className="text-sm font-medium text-cream">Execution Seam Alert</h4>
            <p className="text-xs text-cream/80">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="py-16 text-center space-y-3">
          <Loader2 className="w-6 h-6 animate-spin text-ember mx-auto" />
          <p className="text-xs font-mono uppercase tracking-wider text-muted-cream">
            Loading skills from storage locality...
          </p>
        </div>
      )}

      {/* Candidates View */}
      {!isLoading && activeSubTab === "candidates" && (
        <div className="space-y-4">
          {candidates.length === 0 ? (
            <div className="border border-surface-cork/30 rounded-xl p-12 text-center space-y-3 bg-walnut-surface/10">
              <Sparkles className="w-8 h-8 text-muted-cream/40 mx-auto" />
              <h3 className="text-sm font-medium text-cream">No Candidates Awaiting Review</h3>
              <p className="text-xs text-muted-cream max-w-md mx-auto">
                Candidates are automatically distilled and quarantined upon terminal completion of verified multi-step runs.
              </p>
            </div>
          ) : (
            candidates.map((skill) => (
              <Card
                key={skill.name}
                className="border-surface-cork/60 bg-walnut-surface/40 hover:border-surface-cork transition-all duration-200"
              >
                <CardHeader className="p-5 pb-3">
                  <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="secondary" className="font-mono text-[11px] bg-surface-bark/60 text-cream border-surface-cork">
                          {skill.name}
                        </Badge>
                        <Badge variant="secondary" className="text-[10px] font-mono uppercase bg-amber-500/10 text-amber-300 border-amber-500/20">
                          Quarantined Candidate
                        </Badge>
                        {Boolean(skill.provenance?.evidence_hash) && (
                          <span className="inline-flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                            <ShieldCheck className="w-3 h-3" />
                            Verified Hash: {String(skill.provenance?.evidence_hash).slice(0, 8)}
                          </span>
                        )}
                      </div>
                      <CardTitle className="text-base text-cream mt-1">{skill.description}</CardTitle>
                    </div>

                    {/* Operator Action Buttons */}
                    <div className="flex items-center gap-2 shrink-0 pt-1">
                      <Button
                        size="sm"
                        onClick={() => handleOpenPromote(skill)}
                        className="bg-surface-bark hover:bg-surface-bark/80 text-cream text-xs uppercase tracking-wider rounded-full px-4 border border-cream/20 shadow-sm"
                      >
                        <Check className="w-3.5 h-3.5 mr-1 text-emerald-400" />
                        Promote
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleOpenReject(skill)}
                        className="hover:bg-red-500/10 hover:text-red-300 text-muted-cream text-xs uppercase tracking-wider rounded-full px-3 border border-surface-cork/40"
                      >
                        <X className="w-3.5 h-3.5 mr-1 text-red-400" />
                        Reject
                      </Button>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="p-5 pt-0 space-y-4">
                  {/* Provenance Metadata Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 p-3 rounded-lg bg-black/40 border border-surface-cork/20 text-xs font-mono">
                    <div>
                      <span className="text-muted-cream text-[10px] uppercase block">Attempt ID</span>
                      <span className="text-cream truncate block" title={skill.attempt_id || "None"}>
                        {skill.attempt_id || "None"}
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-cream text-[10px] uppercase block">Tenant Scope</span>
                      <span className="text-cream truncate block">{skill.owner_id || "Shared"}</span>
                    </div>
                    <div>
                      <span className="text-muted-cream text-[10px] uppercase block">Extracted At</span>
                      <span className="text-cream truncate block">
                        {skill.provenance?.extracted_at ? new Date(String(skill.provenance.extracted_at)).toLocaleString() : "Unknown"}
                      </span>
                    </div>
                  </div>

                  {/* Required Tools and Triggers */}
                  <div className="flex flex-wrap items-center gap-4 text-xs">
                    {skill.required_tools.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-muted-cream text-[10px] uppercase font-mono">Tools:</span>
                        {skill.required_tools.map((tool) => (
                          <span
                            key={tool}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-cork/40 text-cream text-[11px] font-mono border border-surface-cork/60"
                          >
                            <Terminal className="w-3 h-3 text-ember" />
                            {tool}
                          </span>
                        ))}
                      </div>
                    )}

                    {skill.triggers.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-muted-cream text-[10px] uppercase font-mono">Triggers:</span>
                        {skill.triggers.map((trigger) => (
                          <span
                            key={trigger}
                            className="px-2 py-0.5 rounded bg-surface-cork/20 text-muted-cream text-[11px] font-mono"
                          >
                            #{trigger}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Collapsible Instruction Preview */}
                  <div className="border-t border-surface-cork/30 pt-3">
                    <button
                      type="button"
                      onClick={() => toggleExpand(skill.name)}
                      className="flex items-center justify-between w-full text-xs font-mono text-muted-cream hover:text-cream transition-colors"
                    >
                      <span className="flex items-center gap-1.5">
                        <FileCode className="w-3.5 h-3.5 text-ember" />
                        Instructions Preview ({skill.instructions.length} chars)
                      </span>
                      {expandedInstructions[skill.name] ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>

                    {expandedInstructions[skill.name] && (
                      <pre className="mt-2 p-3 bg-black/60 rounded border border-surface-cork/40 text-[11px] font-mono text-cream/90 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
                        {skill.instructions}
                      </pre>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Active Library View */}
      {!isLoading && activeSubTab === "active" && (
        <div className="space-y-4">
          {validatedSkills.length === 0 ? (
            <div className="border border-surface-cork/30 rounded-xl p-12 text-center space-y-3 bg-walnut-surface/10">
              <ShieldCheck className="w-8 h-8 text-muted-cream/40 mx-auto" />
              <h3 className="text-sm font-medium text-cream">No Active Validated Skills</h3>
              <p className="text-xs text-muted-cream max-w-md mx-auto">
                Promoted procedural skills will appear here and become eligible for injection into agent execution depth.
              </p>
            </div>
          ) : (
            validatedSkills.map((skill) => (
              <Card key={skill.name} className="border-surface-cork/50 bg-walnut-surface/30">
                <CardHeader className="p-5 pb-3">
                  <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="secondary" className="font-mono text-[11px] bg-surface-bark/40 text-cream border-surface-cork">
                          {skill.name}
                        </Badge>
                        <Badge className="text-[10px] font-mono uppercase bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                          Validated & Active
                        </Badge>
                        <span className="text-[10px] font-mono text-muted-cream bg-surface-cork/30 px-2 py-0.5 rounded">
                          {skill.owner_id ? `Tenant: ${skill.owner_id}` : "Shared System Skill"}
                        </span>
                      </div>
                      <CardTitle className="text-base text-cream mt-1">{skill.description}</CardTitle>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="p-5 pt-0 space-y-3">
                  {/* Audit Review Info */}
                  {skill.review_audit && (
                    <div className="p-3 bg-black/30 rounded border border-surface-cork/20 flex flex-col md:flex-row md:items-center justify-between gap-2 text-xs font-mono text-muted-cream">
                      <div>
                        <span className="text-emerald-400 font-medium">Validated by {skill.review_audit.operator_id}</span>
                        {skill.review_audit.notes && (
                          <span className="text-cream/80 ml-2">&ldquo;{skill.review_audit.notes}&rdquo;</span>
                        )}
                      </div>
                      <span className="text-[10px] text-muted-cream/80">
                        {new Date(skill.review_audit.timestamp).toLocaleString()}
                      </span>
                    </div>
                  )}

                  {/* Required Tools and Triggers */}
                  <div className="flex flex-wrap items-center gap-4 text-xs">
                    {skill.required_tools.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-muted-cream text-[10px] uppercase font-mono">Tools:</span>
                        {skill.required_tools.map((tool) => (
                          <span
                            key={tool}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-cork/40 text-cream text-[11px] font-mono border border-surface-cork/60"
                          >
                            <Terminal className="w-3 h-3 text-ember" />
                            {tool}
                          </span>
                        ))}
                      </div>
                    )}

                    {skill.triggers.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-muted-cream text-[10px] uppercase font-mono">Triggers:</span>
                        {skill.triggers.map((trigger) => (
                          <span
                            key={trigger}
                            className="px-2 py-0.5 rounded bg-surface-cork/20 text-muted-cream text-[11px] font-mono"
                          >
                            #{trigger}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Collapsible Instruction Preview */}
                  <div className="border-t border-surface-cork/30 pt-3">
                    <button
                      type="button"
                      onClick={() => toggleExpand(skill.name)}
                      className="flex items-center justify-between w-full text-xs font-mono text-muted-cream hover:text-cream transition-colors"
                    >
                      <span className="flex items-center gap-1.5">
                        <FileCode className="w-3.5 h-3.5 text-ember" />
                        Instructions Preview ({skill.instructions.length} chars)
                      </span>
                      {expandedInstructions[skill.name] ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>

                    {expandedInstructions[skill.name] && (
                      <pre className="mt-2 p-3 bg-black/60 rounded border border-surface-cork/40 text-[11px] font-mono text-cream/90 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
                        {skill.instructions}
                      </pre>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Archived View */}
      {!isLoading && activeSubTab === "archived" && (
        <div className="space-y-4">
          {rejectedSkills.length === 0 ? (
            <div className="border border-surface-cork/30 rounded-xl p-12 text-center space-y-3 bg-walnut-surface/10">
              <ShieldAlert className="w-8 h-8 text-muted-cream/40 mx-auto" />
              <h3 className="text-sm font-medium text-cream">No Archived or Rejected Skills</h3>
              <p className="text-xs text-muted-cream max-w-md mx-auto">
                Rejected candidates will remain permanently archived here with their evaluation reasons.
              </p>
            </div>
          ) : (
            rejectedSkills.map((skill) => (
              <Card key={skill.name} className="border-red-900/30 bg-walnut-surface/20">
                <CardHeader className="p-5 pb-3">
                  <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="secondary" className="font-mono text-[11px] text-muted-cream border-surface-cork">
                          {skill.name}
                        </Badge>
                        <Badge className="text-[10px] font-mono uppercase bg-red-500/10 text-red-400 border border-red-500/20">
                          Rejected / Archived
                        </Badge>
                      </div>
                      <CardTitle className="text-base text-cream/80 mt-1">{skill.description}</CardTitle>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="p-5 pt-0 space-y-3">
                  {/* Rejection Audit Box */}
                  <div className="p-3 bg-red-950/20 border border-red-900/40 rounded-lg text-xs font-mono space-y-1">
                    <div className="flex items-center justify-between text-muted-cream text-[10px]">
                      <span>Rejected by: {skill.review_audit?.operator_id || "Operator"}</span>
                      <span>
                        {skill.review_audit?.timestamp ? new Date(skill.review_audit.timestamp).toLocaleString() : ""}
                      </span>
                    </div>
                    <p className="text-red-300 font-sans text-xs">
                      Reason: {skill.review_audit?.notes || skill.validation_notes || "No reason recorded"}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Promotion Confirmation Modal */}
      <Dialog open={Boolean(promoteCandidate)} onOpenChange={(open) => !open && setPromoteCandidate(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-lg text-cream flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              Promote Procedural Skill
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-cream">
              Validating will elevate this skill across the validation seam into active agent prompt depth.
            </DialogDescription>
          </DialogHeader>

          {promoteCandidate && (
            <form onSubmit={handleConfirmPromote} className="space-y-4 pt-2">
              <div className="p-3 bg-black/40 rounded border border-surface-cork/40 text-xs font-mono space-y-1">
                <span className="text-muted-cream text-[10px] uppercase block">Target Candidate</span>
                <span className="text-cream font-medium block truncate">{promoteCandidate.name}</span>
                <span className="text-muted-cream text-[11px] block">{promoteCandidate.description}</span>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-mono uppercase tracking-wider text-muted-cream block">
                  Validation Notes (Optional)
                </label>
                <Input
                  value={promotionNotes}
                  onChange={(e) => setPromotionNotes(e.target.value)}
                  placeholder="e.g. Verified safe execution and tool bounds"
                  maxLength={1000}
                  className="bg-black/50 border-surface-cork text-cream placeholder:text-muted-cream/50 text-xs"
                />
              </div>

              {promotionError && (
                <div className="p-2.5 bg-red-950/30 border border-red-900/50 rounded text-xs text-red-300 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                  <span>{promotionError}</span>
                </div>
              )}

              <DialogFooter className="pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setPromoteCandidate(null)}
                  disabled={isPromoting}
                  className="text-xs uppercase tracking-wider text-muted-cream hover:text-cream"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isPromoting}
                  className="bg-emerald-600 hover:bg-emerald-500 text-cream text-xs uppercase tracking-wider rounded-full px-5"
                >
                  {isPromoting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                      Validating...
                    </>
                  ) : (
                    "Confirm Promotion"
                  )}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Rejection Modal */}
      <Dialog open={Boolean(rejectCandidate)} onOpenChange={(open) => !open && setRejectCandidate(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-lg text-cream flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-red-400" />
              Reject Procedural Candidate
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-cream">
              Rejected candidate skills are permanently archived and excluded from active matching depth.
            </DialogDescription>
          </DialogHeader>

          {rejectCandidate && (
            <form onSubmit={handleConfirmReject} className="space-y-4 pt-2">
              <div className="p-3 bg-black/40 rounded border border-surface-cork/40 text-xs font-mono space-y-1">
                <span className="text-muted-cream text-[10px] uppercase block">Target Candidate</span>
                <span className="text-cream font-medium block truncate">{rejectCandidate.name}</span>
                <span className="text-muted-cream text-[11px] block">{rejectCandidate.description}</span>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-mono uppercase tracking-wider text-muted-cream block">
                  Rejection Reason <span className="text-ember">*</span>
                </label>
                <Input
                  required
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  placeholder="e.g. Unsafe parameter sequence or non-deterministic behavior"
                  maxLength={1000}
                  className="bg-black/50 border-surface-cork text-cream placeholder:text-muted-cream/50 text-xs"
                />
              </div>

              {rejectionError && (
                <div className="p-2.5 bg-red-950/30 border border-red-900/50 rounded text-xs text-red-300 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                  <span>{rejectionError}</span>
                </div>
              )}

              <DialogFooter className="pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setRejectCandidate(null)}
                  disabled={isRejecting}
                  className="text-xs uppercase tracking-wider text-muted-cream hover:text-cream"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isRejecting}
                  className="bg-red-700 hover:bg-red-600 text-cream text-xs uppercase tracking-wider rounded-full px-5"
                >
                  {isRejecting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                      Rejecting...
                    </>
                  ) : (
                    "Confirm Rejection"
                  )}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
