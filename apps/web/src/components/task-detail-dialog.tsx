"use client";

import * as React from "react";
import { CheckCircle2, Clock, Play, AlertTriangle, ShieldAlert, Loader2 } from "lucide-react";
import { clientAdapter, type TaskResponse } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

/**
 * Task detail inspector module.
 * Exposes a structured inspection interface for tasks, providing operational depth
 * without leaving the local view context.
 */
interface TaskDetailDialogProps {
  task: TaskResponse | null;
  ownerId: string;
  isOpen: boolean;
  onClose: () => void;
  onRefresh: () => void;
}

export function TaskDetailDialog({
  task,
  ownerId,
  isOpen,
  onClose,
  onRefresh,
}: TaskDetailDialogProps) {
  const [isExecuting, setIsExecuting] = React.useState(false);
  const [isCompleting, setIsCompleting] = React.useState(false);
  const [completeNote, setCompleteNote] = React.useState("");
  const [showCompleteForm, setShowCompleteForm] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);

  if (!task) return null;

  async function handleExecute() {
    if (!task || isExecuting) return;
    setIsExecuting(true);
    setActionError(null);
    try {
      const idempotencyKey = `exec-${task.id}-${Date.now()}`;
      await clientAdapter.executeTask({
        taskId: task.id,
        ownerId,
        idempotencyKey,
      });
      onRefresh();
      onClose();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setIsExecuting(false);
    }
  }

  async function handleComplete(event: React.FormEvent) {
    event.preventDefault();
    if (!task || isCompleting) return;
    setIsCompleting(true);
    setActionError(null);
    try {
      await clientAdapter.completeTask({
        taskId: task.id,
        ownerId,
        confirmationNote: completeNote.trim() || "Manually confirmed completion via web dashboard.",
        targetActionId: task.current_next_action?.id,
      });
      setShowCompleteForm(false);
      setCompleteNote("");
      onRefresh();
      onClose();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Completion confirmation failed");
    } finally {
      setIsCompleting(false);
    }
  }

  const nextAction = task.current_next_action;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between pr-6">
            <Badge variant={task.status === "completed" ? "success" : "default"}>
              {task.status.replace("_", " ")}
            </Badge>
            <span className="text-[10px] text-cream-muted uppercase font-mono tracking-wider">
              ID: {task.id.slice(0, 8)}
            </span>
          </div>
          <DialogTitle className="text-base font-medium mt-2 normal-case tracking-normal">
            {task.title}
          </DialogTitle>
          {task.description && (
            <DialogDescription className="text-xs text-cream-muted mt-1">
              {task.description}
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="space-y-4 py-2 text-xs">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 p-3 rounded-lg bg-[#140c06] border border-surface-cork/40">
            <div>
              <span className="text-[10px] uppercase text-cream-muted block">Priority</span>
              <span className="text-cream font-medium capitalize">{task.priority}</span>
            </div>
            <div>
              <span className="text-[10px] uppercase text-cream-muted block">Due Date</span>
              <span className="text-cream font-medium">
                {task.due_date ? new Date(task.due_date).toLocaleDateString() : "None"}
              </span>
            </div>
            <div>
              <span className="text-[10px] uppercase text-cream-muted block">Created</span>
              <span className="text-cream font-medium">
                {new Date(task.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>

          {/* Current Next Action */}
          {nextAction && (
            <div className="rounded-lg p-3.5 bg-[#181008] border border-surface-cork/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-ember font-medium flex items-center gap-1.5">
                  <Play className="h-3 w-3" /> Concrete Next Action
                </span>
                <Badge
                  variant={
                    nextAction.risk_level === "high"
                      ? "high"
                      : nextAction.risk_level === "medium"
                      ? "medium"
                      : "low"
                  }
                >
                  {nextAction.risk_level} risk
                </Badge>
              </div>
              <p className="text-xs text-cream font-medium">
                {nextAction.description}
              </p>

              {nextAction.tool_hint && (
                <div className="pt-1 text-[11px] font-mono text-cream-muted">
                  Tool: <span className="text-cream">{nextAction.tool_hint}</span>
                </div>
              )}

              {nextAction.tool_args_hint && Object.keys(nextAction.tool_args_hint).length > 0 && (
                <div className="mt-2">
                  <span className="text-[10px] uppercase text-cream-muted block mb-1">
                    Tool Arguments:
                  </span>
                  <pre className="p-2 rounded bg-[#100904] border border-surface-cork/40 text-[10px] font-mono text-cream/90 overflow-x-auto">
                    {JSON.stringify(nextAction.tool_args_hint, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Failure or Recovery Suggestions */}
          {(task.failure_reason || task.recovery_suggestion) && (
            <div className="rounded-lg p-3 bg-[#261006] border border-ember/50 space-y-1.5">
              <div className="flex items-center gap-1.5 text-ember text-[11px] font-medium uppercase tracking-wider">
                <AlertTriangle className="h-3.5 w-3.5" /> Recovery Context
              </div>
              {task.failure_reason && (
                <p className="text-xs text-cream/90">
                  <strong className="text-ember">Failure:</strong> {task.failure_reason}
                </p>
              )}
              {task.recovery_suggestion && (
                <p className="text-xs text-cream-muted">
                  <strong className="text-cream">Recommendation:</strong> {task.recovery_suggestion}
                </p>
              )}
            </div>
          )}

          {/* Inline Complete Form */}
          {showCompleteForm && (
            <form onSubmit={handleComplete} className="space-y-2 p-3 rounded-lg bg-[#140c06] border border-surface-cork">
              <span className="text-[10px] uppercase tracking-wider text-cream-muted block">
                Human Confirmation Evidence Note:
              </span>
              <Input
                value={completeNote}
                onChange={(e) => setCompleteNote(e.target.value)}
                placeholder="Observed evidence or completion note..."
                className="bg-[#100904] text-xs"
                autoFocus
                disabled={isCompleting}
              />
              <div className="flex justify-end gap-2 pt-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowCompleteForm(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={isCompleting}
                  className="bg-emerald-950 border border-emerald-800 text-emerald-200 hover:bg-emerald-900"
                >
                  {isCompleting ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                  Confirm Completed
                </Button>
              </div>
            </form>
          )}

          {actionError && (
            <p className="text-xs text-red-400 p-2 rounded bg-red-950/30 border border-red-900/50">
              {actionError}
            </p>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>

          {task.status !== "completed" && !showCompleteForm && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCompleteForm(true)}
                className="border-emerald-800/80 text-emerald-300 hover:bg-emerald-950/40"
              >
                <CheckCircle2 className="h-3 w-3 mr-1" /> Mark Complete
              </Button>

              {nextAction && !nextAction.completed && (
                <Button
                  size="sm"
                  onClick={handleExecute}
                  disabled={isExecuting}
                  className="bg-surface-bark text-cream border border-surface-cork hover:bg-[#4a301e]"
                >
                  {isExecuting ? (
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  ) : (
                    <Play className="h-3 w-3 mr-1" />
                  )}
                  Execute Action
                </Button>
              )}
            </div>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
