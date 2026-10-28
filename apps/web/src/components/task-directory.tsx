"use client";

import * as React from "react";
import { ListFilter, Search, ChevronRight, Loader2, CheckCircle2, Clock, ArrowUpDown, Filter } from "lucide-react";
import { clientAdapter, type TaskResponse, type TaskStatus } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { TaskDetailDialog } from "@/components/task-detail-dialog";

/**
 * Task directory view module.
 * Provides a comprehensive repository inspection interface across task states.
 * Preserves high locality over search and filtering interactions while allowing
 * users to leverage multi-facet sorting and state filtering with operational depth.
 */
interface TaskDirectoryProps {
  ownerId: string;
  refreshTrigger: number;
  onRefreshNeeded: () => void;
}

type SortOrder = "recent" | "priority" | "due_date";

const FILTER_TABS: { id: string; label: string }[] = [
  { id: "all", label: "All" },
  { id: "actionable", label: "Actionable" },
  { id: "awaiting_approval", label: "Awaiting Approval" },
  { id: "in_progress", label: "In Progress" },
  { id: "completed", label: "Completed" },
  { id: "failed", label: "Failed" },
];

export function TaskDirectory({ ownerId, refreshTrigger, onRefreshNeeded }: TaskDirectoryProps) {
  const [tasks, setTasks] = React.useState<TaskResponse[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [sortOrder, setSortOrder] = React.useState<SortOrder>("recent");

  // Selected task for inspector dialog
  const [selectedTask, setSelectedTask] = React.useState<TaskResponse | null>(null);

  const fetchTasks = React.useCallback(async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const response = await clientAdapter.listTasks(ownerId, 100);
      setTasks(response.tasks);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load tasks");
    } finally {
      setIsLoading(false);
    }
  }, [ownerId]);

  React.useEffect(() => {
    fetchTasks();
  }, [fetchTasks, refreshTrigger]);

  // Compute summary metric counts
  const summaryMetrics = React.useMemo(() => {
    const total = tasks.length;
    const actionable = tasks.filter((t) => t.status !== "completed" && t.status !== "abandoned" && Boolean(t.current_next_action)).length;
    const completed = tasks.filter((t) => t.status === "completed").length;
    const pendingApproval = tasks.filter((t) => t.status === "awaiting_approval").length;
    return { total, actionable, completed, pendingApproval };
  }, [tasks]);

  const filteredTasks = React.useMemo(() => {
    const query = searchQuery.toLowerCase().trim();

    const matches = tasks.filter((t) => {
      const matchesSearch =
        !query ||
        t.title.toLowerCase().includes(query) ||
        t.description.toLowerCase().includes(query);

      let matchesStatus = true;
      if (statusFilter === "actionable") {
        matchesStatus = t.status !== "completed" && t.status !== "abandoned" && Boolean(t.current_next_action);
      } else if (statusFilter === "all") {
        matchesStatus = true;
      } else {
        matchesStatus = t.status === statusFilter;
      }

      return matchesSearch && matchesStatus;
    });

    // Apply sorting
    return matches.sort((a, b) => {
      if (sortOrder === "priority") {
        const priorityScore: Record<string, number> = { urgent: 3, important: 2, routine: 1 };
        const scoreA = priorityScore[a.priority] || 0;
        const scoreB = priorityScore[b.priority] || 0;
        if (scoreA !== scoreB) return scoreB - scoreA;
      } else if (sortOrder === "due_date") {
        if (!a.due_date && !b.due_date) return 0;
        if (!a.due_date) return 1;
        if (!b.due_date) return -1;
        return new Date(a.due_date).getTime() - new Date(b.due_date).getTime();
      }
      // Default: recent (newest created first)
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [tasks, searchQuery, statusFilter, sortOrder]);

  if (isLoading && tasks.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-cream-muted text-xs">
        <Loader2 className="h-4 w-4 animate-spin mr-2" />
        Loading commitments directory...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary Micro-Metric Row */}
      <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-cream-muted">
        <span className="px-2.5 py-1 rounded-full border border-surface-cork/70 bg-[#140c06]">
          Total: <strong className="text-cream">{summaryMetrics.total}</strong>
        </span>
        <span className="px-2.5 py-1 rounded-full border border-surface-cork/70 bg-[#140c06]">
          Actionable: <strong className="text-ember">{summaryMetrics.actionable}</strong>
        </span>
        {summaryMetrics.pendingApproval > 0 && (
          <span className="px-2.5 py-1 rounded-full border border-amber-800/60 bg-amber-950/30 text-amber-300">
            Awaiting Approval: <strong>{summaryMetrics.pendingApproval}</strong>
          </span>
        )}
        <span className="px-2.5 py-1 rounded-full border border-surface-cork/70 bg-[#140c06]">
          Completed: <strong className="text-emerald-400">{summaryMetrics.completed}</strong>
        </span>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col sm:flex-row items-center gap-2">
        <div className="relative w-full sm:flex-1">
          <Search className="absolute left-3 top-3 h-3.5 w-3.5 text-cream-muted" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search commitments and tasks..."
            className="pl-9 h-9 bg-[#140c06] border-surface-cork text-xs"
          />
        </div>

        {/* Sort Order Toggle */}
        <div className="flex items-center gap-1.5 self-end sm:self-auto shrink-0 text-xs">
          <label className="text-[10px] text-cream-muted uppercase tracking-wider flex items-center gap-1">
            <ArrowUpDown className="h-3 w-3" /> Sort:
          </label>
          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value as SortOrder)}
            className="h-8 px-2 rounded-lg bg-[#140c06] border border-surface-cork text-[11px] text-cream focus:outline-none focus:ring-1 focus:ring-cream/40"
          >
            <option value="recent">Recently Created</option>
            <option value="priority">Priority (Urgent first)</option>
            <option value="due_date">Due Date</option>
          </select>
        </div>
      </div>

      {/* State Filter Chips Bar */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {FILTER_TABS.map((tab) => (
          <Button
            key={tab.id}
            variant={statusFilter === tab.id ? "default" : "ghost"}
            size="sm"
            onClick={() => setStatusFilter(tab.id)}
            className="h-7 px-2.5 text-[10px] capitalize shrink-0 font-medium"
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {errorMsg && (
        <div className="p-3 rounded-lg border border-red-900/60 bg-[#240c0a] text-red-300 text-xs flex justify-between items-center">
          <span>{errorMsg}</span>
          <Button variant="outline" size="sm" onClick={fetchTasks}>
            Retry
          </Button>
        </div>
      )}

      {/* Task List */}
      {filteredTasks.length === 0 ? (
        <div className="p-8 rounded-xl border border-surface-cork/40 bg-[#120a05] text-center text-xs text-cream-muted space-y-1">
          <p className="font-medium text-cream">No commitments match the active filter.</p>
          <p className="text-[11px] text-cream-muted/70">
            {searchQuery || statusFilter !== "all"
              ? "Try resetting the search or filter selection."
              : "Capture commitments using the capture box above."}
          </p>
          {(searchQuery || statusFilter !== "all") && (
            <div className="pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSearchQuery("");
                  setStatusFilter("all");
                }}
                className="h-7 text-[10px]"
              >
                Clear Filters
              </Button>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredTasks.map((task) => (
            <div
              key={task.id}
              onClick={() => setSelectedTask(task)}
              className="group flex items-center justify-between p-3.5 rounded-xl border border-surface-cork/60 bg-[#150d07] hover:border-surface-cork hover:bg-[#1a110a] transition-all cursor-pointer"
            >
              <div className="space-y-1 pr-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-cream font-medium">
                    {task.title}
                  </span>
                  <Badge
                    variant={
                      task.status === "completed"
                        ? "success"
                        : task.status === "failed"
                        ? "destructive"
                        : task.status === "awaiting_approval"
                        ? "warning"
                        : "default"
                    }
                    className="text-[9px] py-0 px-1.5"
                  >
                    {task.status.replace("_", " ")}
                  </Badge>
                  {task.priority !== "routine" && (
                    <Badge variant="secondary" className="text-[9px] py-0 px-1 font-mono">
                      {task.priority}
                    </Badge>
                  )}
                </div>

                {task.current_next_action ? (
                  <p className="text-[11px] text-cream-muted line-clamp-1">
                    Action: {task.current_next_action.description}
                  </p>
                ) : (
                  task.description && (
                    <p className="text-[11px] text-cream-muted/70 line-clamp-1">
                      {task.description}
                    </p>
                  )
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <span className="text-[10px] text-cream-muted font-mono">
                  {new Date(task.created_at).toLocaleDateString()}
                </span>
                <ChevronRight className="h-4 w-4 text-cream-muted/60 group-hover:text-cream" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail Dialog */}
      <TaskDetailDialog
        task={selectedTask}
        ownerId={ownerId}
        isOpen={Boolean(selectedTask)}
        onClose={() => setSelectedTask(null)}
        onRefresh={() => {
          fetchTasks();
          onRefreshNeeded();
        }}
      />
    </div>
  );
}
