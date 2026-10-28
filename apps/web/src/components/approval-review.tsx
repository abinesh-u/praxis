"use client";

import * as React from "react";
import { Check, X, ShieldAlert, ChevronDown, ChevronUp, Loader2, Clock, AlertTriangle } from "lucide-react";
import { clientAdapter, type ApprovalResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

/**
 * Approval review view module.
 * Establishes an authorization review interface at the execution security seam.
 * Enforces explicit human agency over consequential operations with high locality
 * and prevents disclosure of sensitive secrets across preview layers.
 */
interface ApprovalReviewProps {
  ownerId: string;
  onDecision: () => void;
}

const REJECTION_CHIPS = [
  "Postpone for later",
  "Incorrect arguments",
  "Unintended scope",
  "No longer needed",
];

function sanitizeArguments(args: Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!args) return {};
  const SENSITIVE_KEYS = ["token", "secret", "password", "key", "authorization", "bearer", "api_key", "credential"];
  const sanitized: Record<string, unknown> = {};

  for (const [k, v] of Object.entries(args)) {
    const lowerKey = k.toLowerCase();
    if (SENSITIVE_KEYS.some((sk) => lowerKey.includes(sk))) {
      sanitized[k] = "•••••••• [REDACTED]";
    } else if (typeof v === "object" && v !== null && !Array.isArray(v)) {
      sanitized[k] = sanitizeArguments(v as Record<string, unknown>);
    } else {
      sanitized[k] = v;
    }
  }
  return sanitized;
}

function getExpiryInfo(expiresAtStr: string): { isExpired: boolean; label: string; badgeVariant: "destructive" | "warning" | "secondary" } {
  try {
    const expiresAt = new Date(expiresAtStr).getTime();
    const now = Date.now();
    const diffMs = expiresAt - now;

    if (diffMs <= 0 || isNaN(diffMs)) {
      return { isExpired: true, label: "Expired", badgeVariant: "destructive" };
    }

    const diffMins = Math.floor(diffMs / (1000 * 60));
    if (diffMins < 60) {
      const isUrgent = diffMins < 15;
      return {
        isExpired: false,
        label: `Expires in ${diffMins}m`,
        badgeVariant: isUrgent ? "warning" : "secondary",
      };
    }

    const diffHours = Math.floor(diffMins / 60);
    const remainingMins = diffMins % 60;
    return {
      isExpired: false,
      label: `Expires in ${diffHours}h ${remainingMins}m`,
      badgeVariant: "secondary",
    };
  } catch {
    return { isExpired: false, label: "Time limited", badgeVariant: "secondary" };
  }
}

export function ApprovalReview({ ownerId, onDecision }: ApprovalReviewProps) {
  const [approvals, setApprovals] = React.useState<ApprovalResponse[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  // Expanded args state by approval ID
  const [expandedArgs, setExpandedArgs] = React.useState<Record<string, boolean>>({});

  // Rejection input state
  const [rejectingId, setRejectingId] = React.useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = React.useState("");
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const fetchApprovals = React.useCallback(async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const response = await clientAdapter.listApprovals(ownerId);
      setApprovals(response.approvals);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load pending approvals");
    } finally {
      setIsLoading(false);
    }
  }, [ownerId]);

  React.useEffect(() => {
    fetchApprovals();
  }, [fetchApprovals]);

  function toggleArgs(id: string) {
    setExpandedArgs((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  async function handleApprove(approvalId: string) {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await clientAdapter.decideApproval({
        approvalId,
        ownerId,
        decision: "approve",
      });
      fetchApprovals();
      onDecision();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Approval submission failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleReject(approvalId: string) {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await clientAdapter.decideApproval({
        approvalId,
        ownerId,
        decision: "reject",
        rejectionReason: rejectionReason.trim() || "Rejected by user via web interface",
        fatalRejection: false,
      });
      setRejectingId(null);
      setRejectionReason("");
      fetchApprovals();
      onDecision();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Rejection submission failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-cream-muted text-xs">
        <Loader2 className="h-4 w-4 animate-spin mr-2" />
        Checking pending authorization requests...
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div className="p-4 rounded-xl border border-red-900/60 bg-[#240c0a] text-red-300 text-xs flex items-center justify-between">
        <span>{errorMsg}</span>
        <Button variant="outline" size="sm" onClick={fetchApprovals}>
          Retry
        </Button>
      </div>
    );
  }

  if (approvals.length === 0) {
    return (
      <div className="rounded-xl border border-surface-cork/40 bg-[#120a05] p-8 text-center text-xs text-cream-muted">
        <ShieldAlert className="h-8 w-8 mx-auto text-surface-cork mb-2" />
        <p className="font-medium uppercase tracking-wider text-[11px] text-cream">
          No Pending Approvals
        </p>
        <p className="mt-1 text-cream-muted/70">
          All consequential and external operations are authorized or completed.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-xs uppercase font-medium tracking-wider text-cream flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-ember" />
          Pending Approvals ({approvals.length})
        </h4>
        <span className="text-[10px] text-cream-muted uppercase">
          Explicit approval required for execution
        </span>
      </div>

      <div className="space-y-3">
        {approvals.map((approval) => {
          const isExpanded = expandedArgs[approval.id];
          const isCurrentRejecting = rejectingId === approval.id;
          const expiryInfo = getExpiryInfo(approval.expires_at);
          const sanitizedArgs = sanitizeArguments(approval.canonical_args);

          return (
            <Card key={approval.id} className="border-surface-cork bg-[#160e08]">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        approval.risk_level === "high"
                          ? "high"
                          : approval.risk_level === "medium"
                          ? "medium"
                          : "low"
                      }
                    >
                      {approval.risk_level} risk
                    </Badge>
                    <span className="text-[10px] font-mono text-cream-muted">
                      ID: {approval.id.slice(0, 8)}
                    </span>
                  </div>
                  <Badge variant={expiryInfo.badgeVariant} className="font-mono text-[9px] flex items-center gap-1">
                    <Clock className="h-2.5 w-2.5" />
                    {expiryInfo.label}
                  </Badge>
                </div>
                <CardTitle className="text-xs font-mono normal-case tracking-normal mt-2 text-cream">
                  Tool: <span className="text-ember font-bold">{approval.tool_name}</span>
                </CardTitle>
                <CardDescription className="text-xs text-cream/90 font-serif italic">
                  &ldquo;{approval.justification}&rdquo;
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-3 pt-0">
                {/* Collapsible Structured Canonical Arguments */}
                <div className="rounded-lg bg-[#100904] border border-surface-cork/50 p-2.5">
                  <button
                    type="button"
                    onClick={() => toggleArgs(approval.id)}
                    className="flex w-full items-center justify-between text-[10px] uppercase tracking-wider text-cream-muted hover:text-cream transition-colors"
                  >
                    <span>Canonical Arguments ({Object.keys(sanitizedArgs).length})</span>
                    {isExpanded ? (
                      <ChevronUp className="h-3 w-3" />
                    ) : (
                      <ChevronDown className="h-3 w-3" />
                    )}
                  </button>

                  {isExpanded && (
                    <div className="mt-2 space-y-1.5 pt-1 border-t border-surface-cork/30">
                      <pre className="text-[10px] font-mono text-cream/90 overflow-x-auto p-2 rounded bg-black/40 border border-surface-cork/30 max-h-48">
                        {JSON.stringify(sanitizedArgs, null, 2)}
                      </pre>
                      <p className="text-[9px] text-cream-muted/70 italic">
                        Note: Sensitive tokens and credentials are masked from preview depth.
                      </p>
                    </div>
                  )}
                </div>

                {/* Reject note prompt if active */}
                {isCurrentRejecting && (
                  <div className="space-y-2 p-3 rounded-lg bg-[#240c0a] border border-red-900/50">
                    <span className="text-[10px] uppercase text-red-300 block font-medium">
                      Select reason or type custom feedback:
                    </span>
                    <div className="flex flex-wrap gap-1.5 pb-1">
                      {REJECTION_CHIPS.map((chip) => (
                        <button
                          key={chip}
                          type="button"
                          onClick={() => setRejectionReason(chip)}
                          className="px-2 py-0.5 rounded-full border border-red-900/70 bg-[#1e0a09] text-[10px] text-red-200 hover:border-red-700"
                        >
                          {chip}
                        </button>
                      ))}
                    </div>
                    <Input
                      value={rejectionReason}
                      onChange={(e) => setRejectionReason(e.target.value)}
                      placeholder="Why is this action rejected?"
                      className="bg-[#100904] text-xs"
                      autoFocus
                      disabled={isSubmitting}
                    />
                    <div className="flex justify-end gap-2 pt-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setRejectingId(null);
                          setRejectionReason("");
                        }}
                      >
                        Cancel
                      </Button>
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        onClick={() => handleReject(approval.id)}
                        disabled={isSubmitting}
                      >
                        {isSubmitting ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                        Confirm Rejection
                      </Button>
                    </div>
                  </div>
                )}

                {/* Action buttons */}
                {!isCurrentRejecting && (
                  <div className="flex items-center justify-between pt-1">
                    {expiryInfo.isExpired ? (
                      <span className="text-[11px] text-red-400 font-medium flex items-center gap-1">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        Expired token cannot authorize execution
                      </span>
                    ) : (
                      <div />
                    )}

                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setRejectingId(approval.id)}
                        disabled={isSubmitting}
                        className="border-red-900/60 text-red-300 hover:bg-red-950/40"
                      >
                        <X className="h-3 w-3 mr-1" />
                        Reject
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => handleApprove(approval.id)}
                        disabled={isSubmitting || expiryInfo.isExpired}
                        className="bg-surface-bark text-cream border border-surface-cork hover:bg-[#4a301e] disabled:opacity-40"
                      >
                        {isSubmitting ? (
                          <Loader2 className="h-3 w-3 animate-spin mr-1" />
                        ) : (
                          <Check className="h-3 w-3 mr-1" />
                        )}
                        Approve & Grant Token
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
