"use client";

import * as React from "react";
import { Check, X, ShieldAlert, ChevronDown, ChevronUp, Loader2, AlertCircle } from "lucide-react";
import { clientAdapter, type ApprovalResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

/**
 * Approval review view module.
 * Establishes an authorization review interface at the execution security seam.
 * Enforces explicit human agency over consequential operations with high locality.
 */
interface ApprovalReviewProps {
  ownerId: string;
  onDecision: () => void;
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

          return (
            <Card key={approval.id} className="border-surface-cork bg-[#160e08]">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
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
                  <span className="text-[10px] text-cream-muted font-mono uppercase">
                    Expires: {new Date(approval.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <CardTitle className="text-xs font-mono normal-case tracking-normal mt-2 text-cream">
                  Tool: <span className="text-ember font-bold">{approval.tool_name}</span>
                </CardTitle>
                <CardDescription className="text-xs text-cream/90 font-serif italic">
                  &ldquo;{approval.justification}&rdquo;
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-3 pt-0">
                {/* Collapsible Canonical Args */}
                <div className="rounded-lg bg-[#100904] border border-surface-cork/50 p-2.5">
                  <button
                    type="button"
                    onClick={() => toggleArgs(approval.id)}
                    className="flex w-full items-center justify-between text-[10px] uppercase tracking-wider text-cream-muted hover:text-cream transition-colors"
                  >
                    <span>Canonical Arguments ({Object.keys(approval.canonical_args || {}).length})</span>
                    {isExpanded ? (
                      <ChevronUp className="h-3 w-3" />
                    ) : (
                      <ChevronDown className="h-3 w-3" />
                    )}
                  </button>

                  {isExpanded && (
                    <pre className="mt-2 text-[10px] font-mono text-cream/90 overflow-x-auto p-2 rounded bg-black/40 border border-surface-cork/30">
                      {JSON.stringify(approval.canonical_args, null, 2)}
                    </pre>
                  )}
                </div>

                {/* Reject note prompt if active */}
                {isCurrentRejecting && (
                  <div className="space-y-2 p-2.5 rounded-lg bg-[#240c0a] border border-red-900/50">
                    <span className="text-[10px] uppercase text-red-300 block">
                      Rejection Reason (Optional):
                    </span>
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
                        onClick={() => setRejectingId(null)}
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
                        Confirm Rejection
                      </Button>
                    </div>
                  </div>
                )}

                {/* Action buttons */}
                {!isCurrentRejecting && (
                  <div className="flex items-center justify-end gap-2 pt-1">
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
                      disabled={isSubmitting}
                      className="bg-surface-bark text-cream border border-surface-cork hover:bg-[#4a301e]"
                    >
                      {isSubmitting ? (
                        <Loader2 className="h-3 w-3 animate-spin mr-1" />
                      ) : (
                        <Check className="h-3 w-3 mr-1" />
                      )}
                      Approve & Grant Token
                    </Button>
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
