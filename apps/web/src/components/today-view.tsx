"use client";

import * as React from "react";
import {
  CheckCircle2,
  Play,
  Clock,
  AlertCircle,
  HelpCircle,
  ChevronRight,
  Loader2,
  Calendar,
  Sparkles,
} from "lucide-react";
import {
  clientAdapter,
  type TodayResponse,
  type AgendaItemResponse,
  type TaskResponse,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RecoveryBanner } from "@/components/recovery-banner";
import { TaskDetailDialog } from "@/components/task-detail-dialog";

/**
 * Today focus view module.
 * Structures the daily execution agenda to reduce cognitive friction and make
 * the immediate next step obvious. Maintains high locality over task interactions.
 */
interface TodayViewProps {
  ownerId: string;
  refreshTrigger: number;
  onRefreshNeeded: () => void;
}

export function TodayView({ ownerId, refreshTrigger, onRefreshNeeded }: TodayViewProps) {
  const [agenda, setAgenda] = React.useState<TodayResponse | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  // Inspector dialog state
  const [selectedTask, setSelectedTask] = React.useState<TaskResponse | null>(null);

  // Execution state per task ID
  const [executingTaskId, setExecutingTaskId] = React.useState<string | null>(null);

  const fetchAgenda = React.useCallback(async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const response = await clientAdapter.getToday(ownerId);
      setAgenda(response);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load agenda");
    } finally {
      setIsLoading(false);
    }
  }, [ownerId]);

  React.useEffect(() => {
    fetchAgenda();
  }, [fetchAgenda, refreshTrigger]);

  async function handleQuickExecute(item: AgendaItemResponse, e: React.MouseEvent) {
    e.stopPropagation();
    if (executingTaskId) return;

    setExecutingTaskId(item.task.id);
    try {
      const idempotencyKey = `exec-${item.task.id}-${Date.now()}`;
      await clientAdapter.executeTask({
        taskId: item.task.id,
        ownerId,
        idempotencyKey,
      });
      fetchAgenda();
      onRefreshNeeded();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Quick execution failed");
    } finally {
      setExecutingTaskId(null);
    }
  }

  if (isLoading && !agenda) {
    return (
      <div className="flex items-center justify-center py-16 text-cream-muted text-xs">
        <Loader2 className="h-4 w-4 animate-spin mr-2" />
        Loading daily agenda...
      </div>
    );
  }

  if (errorMsg && !agenda) {
    return (
      <div className="p-4 rounded-xl border border-red-900/60 bg-[#240c0a] text-red-300 text-xs flex items-center justify-between">
        <span>{errorMsg}</span>
        <Button variant="outline" size="sm" onClick={fetchAgenda}>
          Retry
        </Button>
      </div>
    );
  }

  const actionable = agenda?.actionable || [];
  const waiting = agenda?.waiting || [];
  const primaryItem = actionable[0];
  const remainingActionable = actionable.slice(1);

  return (
    <div className="space-y-6">
      {/* Primary Immediate Next Step Banner */}
      {primaryItem ? (
        <Card className="border-surface-cork/90 bg-[#191008] shadow-lg relative overflow-hidden">
          <div className="absolute top-0 left-0 h-1 w-full bg-gradient-to-r from-ember via-[#ffedd7] to-surface-bark" />
          <CardHeader className="pb-2 pt-5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold tracking-widest text-ember flex items-center gap-1.5">
                <Sparkles className="h-3 w-3" /> Next Immediate Focus
              </span>
              <Badge variant={primaryItem.task.current_next_action?.risk_level === "high" ? "high" : "default"}>
                {primaryItem.task.current_next_action?.risk_level || "low"} risk
              </Badge>
            </div>
            <CardTitle className="text-base text-cream normal-case tracking-normal mt-1">
              {primaryItem.task.title}
            </CardTitle>
            {primaryItem.task.description && (
              <CardDescription className="text-xs text-cream-muted line-clamp-2">
                {primaryItem.task.description}
              </CardDescription>
            )}
          </CardHeader>

          <CardContent className="space-y-4 pt-2">
            {/* Concrete Action Card */}
            {primaryItem.task.current_next_action && (
              <div className="p-3.5 rounded-lg bg-[#120a04] border border-surface-cork/70 flex items-center justify-between gap-3">
                <div className="space-y-1">
                  <span className="text-[10px] uppercase tracking-wider text-cream-muted block">
                    Target Action:
                  </span>
                  <p className="text-xs text-cream font-medium">
                    {primaryItem.task.current_next_action.description}
                  </p>
                </div>
                <Button
                  onClick={(e) => handleQuickExecute(primaryItem, e)}
                  disabled={Boolean(executingTaskId)}
                  size="sm"
                  className="shrink-0 bg-surface-bark hover:bg-[#4a301e] border border-surface-cork text-cream"
                >
                  {executingTaskId === primaryItem.task.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                  ) : (
                    <Play className="h-3.5 w-3.5 mr-1" />
                  )}
                  Execute Now
                </Button>
              </div>
            )}

            {/* Check for outcome_unknown attempt */}
            {primaryItem.attempt && (
              <RecoveryBanner
                taskId={primaryItem.task.id}
                attempt={primaryItem.attempt}
                ownerId={ownerId}
                onReconciled={fetchAgenda}
              />
            )}

            <div className="flex items-center justify-between pt-1 border-t border-surface-cork/30">
              <span className="text-[10px] font-mono text-cream-muted">
                Task ID: {primaryItem.task.id.slice(0, 8)}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedTask(primaryItem.task)}
                className="text-[11px] text-cream-muted hover:text-cream h-7 px-2"
              >
                Inspect Task Details <ChevronRight className="h-3 w-3 ml-1" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="rounded-xl border border-surface-cork/40 bg-[#120a05] p-8 text-center text-xs text-cream-muted">
          <Calendar className="h-8 w-8 mx-auto text-surface-cork mb-2" />
          <p className="font-medium uppercase tracking-wider text-[11px] text-cream">
            All Clear For Today
          </p>
          <p className="mt-1 text-cream-muted/70">
            No actionable next actions are currently waiting. Capture a new task above anytime.
          </p>
        </div>
      )}

      {/* Actionable List */}
      {remainingActionable.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs uppercase font-medium tracking-wider text-cream flex items-center justify-between">
            <span>Also Actionable ({remainingActionable.length})</span>
            <span className="text-[10px] text-cream-muted">Ready to proceed</span>
          </h4>

          <div className="space-y-2">
            {remainingActionable.map((item) => (
              <div
                key={item.task.id}
                onClick={() => setSelectedTask(item.task)}
                className="group flex items-center justify-between p-3.5 rounded-xl border border-surface-cork/60 bg-[#150d07] hover:border-surface-cork hover:bg-[#1a110a] transition-all cursor-pointer"
              >
                <div className="space-y-1 pr-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-cream font-medium group-hover:text-cream">
                      {item.task.title}
                    </span>
                    <Badge variant="default" className="text-[9px] py-0 px-1.5">
                      {item.task.priority}
                    </Badge>
                  </div>
                  {item.task.current_next_action && (
                    <p className="text-[11px] text-cream-muted line-clamp-1">
                      → {item.task.current_next_action.description}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    onClick={(e) => handleQuickExecute(item, e)}
                    disabled={Boolean(executingTaskId)}
                    size="sm"
                    variant="outline"
                    className="h-7 px-2.5 text-[10px] border-surface-cork text-cream hover:bg-surface-bark"
                  >
                    {executingTaskId === item.task.id ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Play className="h-3 w-3 mr-1" />
                    )}
                    Execute
                  </Button>
                  <ChevronRight className="h-4 w-4 text-cream-muted/60 group-hover:text-cream" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Waiting List */}
      {waiting.length > 0 && (
        <div className="space-y-3 pt-2">
          <h4 className="text-xs uppercase font-medium tracking-wider text-cream-muted flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" /> Waiting or Blocked ({waiting.length})
            </span>
            <span className="text-[10px] text-cream-muted/70">Awaiting prerequisites</span>
          </h4>

          <div className="space-y-2">
            {waiting.map((item) => (
              <div
                key={item.task.id}
                onClick={() => setSelectedTask(item.task)}
                className="flex items-center justify-between p-3.5 rounded-xl border border-surface-cork/40 bg-[#120a05] opacity-75 hover:opacity-100 transition-opacity cursor-pointer"
              >
                <div className="space-y-1">
                  <span className="text-xs text-cream/90 font-medium block">
                    {item.task.title}
                  </span>
                  <div className="flex items-center gap-2 text-[10px] text-cream-muted">
                    <span className="capitalize">{item.task.status.replace("_", " ")}</span>
                    {item.waiting_reason && (
                      <span className="text-amber-300/80 italic font-serif">
                        — {item.waiting_reason}
                      </span>
                    )}
                  </div>
                </div>

                <ChevronRight className="h-4 w-4 text-cream-muted/40" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Detail Dialog */}
      <TaskDetailDialog
        task={selectedTask}
        ownerId={ownerId}
        isOpen={Boolean(selectedTask)}
        onClose={() => setSelectedTask(null)}
        onRefresh={() => {
          fetchAgenda();
          onRefreshNeeded();
        }}
      />
    </div>
  );
}
