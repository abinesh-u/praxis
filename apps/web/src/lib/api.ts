/**
 * Client transport adapter module for backend communication.
 * Establishes a typed data interface across the network seam to leverage
 * backend state transitions with high architectural depth and local caller clarity.
 */

export type TaskStatus =
  | "planned"
  | "in_progress"
  | "blocked"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "abandoned";

export type Priority = "routine" | "important" | "urgent";

export type ActionRiskLevel = "low" | "medium" | "high";

export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired";

export interface NextActionResponse {
  id: string;
  task_id: string;
  description: string;
  tool_hint: string | null;
  tool_args_hint: Record<string, unknown> | null;
  risk_level: ActionRiskLevel;
  completed: boolean;
  completed_at: string | null;
  evidence_id: string | null;
  sort_order: number;
  execution_attempts: number;
}

export interface TaskResponse {
  id: string;
  owner_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: Priority;
  due_date: string | null;
  scheduled_date: string | null;
  completed_at: string | null;
  deferred_until: string | null;
  failure_reason: string | null;
  recovery_suggestion: string | null;
  current_next_action: NextActionResponse | null;
  created_at: string;
  updated_at: string;
}

export interface CommitmentResponse {
  id: string;
  owner_id: string;
  raw_text: string;
  source: string;
  captured_at: string;
  interpreted_intent: string | null;
  clarification_needed: boolean;
  clarification_prompt: string | null;
}

export interface CaptureTaskResponse {
  commitment: CommitmentResponse;
  task: TaskResponse | null;
  clarification_needed: boolean;
  clarification_prompt: string | null;
}

export interface AttemptSummaryResponse {
  id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  provider_request_id: string | null;
  evidence_id: string | null;
  error: string | null;
}

export interface AgendaItemResponse {
  task: TaskResponse;
  is_blocked: boolean;
  waiting_reason: string | null;
  attempt: AttemptSummaryResponse | null;
}

export interface TodayResponse {
  date: string;
  actionable: AgendaItemResponse[];
  waiting: AgendaItemResponse[];
}

export interface TaskListResponse {
  tasks: TaskResponse[];
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ApprovalResponse {
  id: string;
  task_id: string;
  tool_name: string;
  canonical_args: Record<string, unknown>;
  risk_level: ActionRiskLevel;
  justification: string;
  status: ApprovalStatus;
  expires_at: string;
  decided_at: string | null;
  rejection_reason: string | null;
}

export interface ApprovalListResponse {
  approvals: ApprovalResponse[];
}

export interface ApprovalDecisionResponse {
  approval: ApprovalResponse;
  task: TaskResponse;
}

export interface ExecutionResponse {
  task: TaskResponse;
  attempt_id: string | null;
  attempt_status: string | null;
  outcome_status: string;
  output: unknown;
  error: string | null;
  provider_request_id: string | null;
  approval: ApprovalResponse | null;
  approval_token: string | null;
}

export interface TransportErrorDetail {
  message: string;
  code?: string;
  details?: Record<string, unknown>;
}

export class TransportError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details?: Record<string, unknown>;

  constructor(status: number, errorDetail: TransportErrorDetail) {
    super(errorDetail.message);
    this.name = "TransportError";
    this.status = status;
    this.code = errorDetail.code;
    this.details = errorDetail.details;
  }
}

const DEFAULT_BASE_PATH = "/api/backend";

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  basePath = DEFAULT_BASE_PATH
): Promise<T> {
  const url = `${basePath}${path}`;
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail: TransportErrorDetail;
    try {
      const errorPayload = await response.json();
      if (errorPayload.detail) {
        if (typeof errorPayload.detail === "string") {
          errorDetail = { message: errorPayload.detail };
        } else {
          errorDetail = {
            message: errorPayload.detail.message || "Operation rejected by backend",
            code: errorPayload.detail.code,
            details: errorPayload.detail.details,
          };
        }
      } else {
        errorDetail = { message: `Request failed with status ${response.status}` };
      }
    } catch {
      errorDetail = { message: `Request failed with status ${response.status}: ${response.statusText}` };
    }
    throw new TransportError(response.status, errorDetail);
  }

  return response.json() as Promise<T>;
}

export const clientAdapter = {
  async getToday(ownerId: string, at?: string): Promise<TodayResponse> {
    const params = new URLSearchParams({ owner_id: ownerId });
    if (at) params.set("at", at);
    return requestJson<TodayResponse>(`/tasks/today?${params.toString()}`);
  },

  async captureTask(params: {
    ownerId: string;
    rawText: string;
    source?: string;
    userTimezone?: string;
    idempotencyKey?: string;
    referenceTime?: string;
  }): Promise<CaptureTaskResponse> {
    return requestJson<CaptureTaskResponse>("/tasks", {
      method: "POST",
      body: JSON.stringify({
        owner_id: params.ownerId,
        raw_text: params.rawText,
        source: params.source || "web",
        user_timezone: params.userTimezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        idempotency_key: params.idempotencyKey,
        reference_time: params.referenceTime,
      }),
    });
  },

  async clarifyCommitment(params: {
    commitmentId: string;
    ownerId: string;
    clarificationResponse: string;
    userTimezone?: string;
    referenceTime?: string;
  }): Promise<CaptureTaskResponse> {
    return requestJson<CaptureTaskResponse>(`/commitments/${params.commitmentId}/clarify`, {
      method: "POST",
      body: JSON.stringify({
        owner_id: params.ownerId,
        clarification_response: params.clarificationResponse,
        user_timezone: params.userTimezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        reference_time: params.referenceTime,
      }),
    });
  },

  async listTasks(ownerId: string, limit = 50, offset = 0): Promise<TaskListResponse> {
    const params = new URLSearchParams({
      owner_id: ownerId,
      limit: String(limit),
      offset: String(offset),
    });
    return requestJson<TaskListResponse>(`/tasks?${params.toString()}`);
  },

  async getTask(taskId: string, ownerId: string): Promise<TaskResponse> {
    const params = new URLSearchParams({ owner_id: ownerId });
    return requestJson<TaskResponse>(`/tasks/${taskId}?${params.toString()}`);
  },

  async completeTask(params: {
    taskId: string;
    ownerId: string;
    confirmationNote: string;
    targetActionId?: string;
  }): Promise<TaskResponse> {
    return requestJson<TaskResponse>(`/tasks/${params.taskId}/complete`, {
      method: "POST",
      body: JSON.stringify({
        owner_id: params.ownerId,
        confirmation_note: params.confirmationNote,
        target_action_id: params.targetActionId,
      }),
    });
  },

  async executeTask(params: {
    taskId: string;
    ownerId: string;
    idempotencyKey: string;
    approvalToken?: string;
    workspaceRoot?: string;
  }): Promise<ExecutionResponse> {
    return requestJson<ExecutionResponse>(`/tasks/${params.taskId}/execute`, {
      method: "POST",
      body: JSON.stringify({
        owner_id: params.ownerId,
        idempotency_key: params.idempotencyKey,
        approval_token: params.approvalToken,
        workspace_root: params.workspaceRoot,
      }),
    });
  },

  async reconcileTask(params: {
    taskId: string;
    ownerId: string;
    attemptId: string;
  }): Promise<ExecutionResponse> {
    return requestJson<ExecutionResponse>(`/tasks/${params.taskId}/reconcile`, {
      method: "POST",
      body: JSON.stringify({
        owner_id: params.ownerId,
        attempt_id: params.attemptId,
      }),
    });
  },

  async listApprovals(ownerId: string): Promise<ApprovalListResponse> {
    const params = new URLSearchParams({ owner_id: ownerId });
    return requestJson<ApprovalListResponse>(`/approvals?${params.toString()}`);
  },

  async decideApproval(params: {
    approvalId: string;
    ownerId: string;
    decision: "approve" | "reject";
    rejectionReason?: string;
    fatalRejection?: boolean;
  }): Promise<ApprovalDecisionResponse> {
    return requestJson<ApprovalDecisionResponse>(`/approvals/${params.approvalId}/decision`, {
      method: "POST",
      body: JSON.stringify({
        owner_id: params.ownerId,
        decision: params.decision,
        rejection_reason: params.rejectionReason,
        fatal_rejection: params.fatalRejection || false,
      }),
    });
  },
};
