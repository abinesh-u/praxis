"use client";

import * as React from "react";
import { AlertCircle, RefreshCw, Loader2 } from "lucide-react";
import { clientAdapter, type AttemptSummaryResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";

/**
 * Outcome reconciliation recovery module.
 * Exposes an interface for recovering from uncertain attempt states without
 * duplicating side-effects across the network seam, preserving operational depth.
 */
interface RecoveryBannerProps {
  taskId: string;
  attempt: AttemptSummaryResponse;
  ownerId: string;
  onReconciled: () => void;
}

export function RecoveryBanner({
  taskId,
  attempt,
  ownerId,
  onReconciled,
}: RecoveryBannerProps) {
  const [isReconciling, setIsReconciling] = React.useState(false);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  if (attempt.status !== "outcome_unknown" && attempt.status !== "running") {
    return null;
  }

  async function handleReconcile() {
    if (isReconciling) return;
    setIsReconciling(true);
    setErrorMsg(null);
    try {
      await clientAdapter.reconcileTask({
        taskId,
        ownerId,
        attemptId: attempt.id,
      });
      onReconciled();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Reconciliation query failed");
    } finally {
      setIsReconciling(false);
    }
  }

  return (
    <div className="rounded-xl border border-ember/60 bg-[#241005] p-4 text-xs space-y-2.5">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <AlertCircle className="h-4 w-4 text-ember shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h5 className="font-medium uppercase tracking-wider text-[11px] text-cream">
              Uncertain Execution State (Outcome Unknown)
            </h5>
            <p className="text-cream-muted leading-relaxed">
              The external provider has not returned authoritative evidence of completion.
              To avoid duplicate execution, Praxis restricts actions to read-only status reconciliation.
            </p>
            {attempt.error && (
              <p className="text-[11px] font-mono text-red-300">
                Details: {attempt.error}
              </p>
            )}
          </div>
        </div>

        <Button
          onClick={handleReconcile}
          disabled={isReconciling}
          size="sm"
          className="shrink-0 bg-surface-bark hover:bg-[#4a301e] border border-surface-cork text-cream"
        >
          {isReconciling ? (
            <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
          ) : (
            <RefreshCw className="h-3 w-3 mr-1.5" />
          )}
          Reconcile Status
        </Button>
      </div>

      {errorMsg && (
        <p className="text-[11px] text-red-400 font-mono pl-6">
          {errorMsg}
        </p>
      )}
    </div>
  );
}
