"use client";

import * as React from "react";
import { ListFilter, Search, ChevronRight, Loader2, CheckCircle2, Clock } from "lucide-react";
import { clientAdapter, type TaskResponse, type TaskStatus } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { TaskDetailDialog } from "@/components/task-detail-dialog";

/**
 * Task directory view module.
 * Provides a comprehensive repository inspection interface across task states.
 * Preserves high locality over search and filtering interactions.
 */
interface TaskDirectoryProps {
  ownerId: string;
  refreshTrigger: number;
  onRefreshNeeded: () => void;
}

export function TaskDirectory({ ownerId, refreshTrigger, onRefreshNeeded }: TaskDirectoryProps) {
  const [tasks, setTasks] = React.useState<TaskResponse[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<string>("all");

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

  const filteredTasks = React.useMemo(() => {
    return tasks.filter((t) => {
      const matchesSearch =
        t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.description.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && t.status !== "completed" && t.status !== "abandoned") ||
        t.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [tasks, searchQuery, statusFilter]);

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

        <div className="flex items-center gap-1 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
          {["all", "active", "completed", "failed"].map((filter) => (
            <Button
              key={filter}
              variant={statusFilter === filter ? "default" : "ghost"}
              size="sm"
              onClick={() => setStatusFilter(filter)}
              className="h-8 px-3 text-[11px] capitalize shrink-0"
            >
              {filter}
            </Button>
          ))}
        </div>
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
        <div className="p-8 rounded-xl border border-surface-cork/40 bg-[#120a05] text-center text-xs text-cream-muted">
          No commitments found matching the current criteria.
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
                        : "default"
                    }
                    className="text-[9px] py-0 px-1.5"
                  >
                    {task.status.replace("_", " ")}
                  </Badge>
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
