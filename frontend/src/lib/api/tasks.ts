import { apiRequest, createIdempotencyKeyForAction } from "@/lib/api/client";

export type TaskType = "call" | "meeting" | "reminder" | "follow_up";
export type TaskStatus = "open" | "done" | "cancelled" | "paused";
export type ApprovalStatus = "not_required" | "pending" | "approved" | "rejected";

export interface Task {
  id: string;
  tenant_id: string;
  lead_id: string;
  title: string;
  notes: string | null;
  type: TaskType;
  status: TaskStatus;
  due_at: string;
  assigned_user_id: string | null;
  team_id: string | null;
  requires_approval: boolean;
  approval_status: ApprovalStatus;
  approved_by_user_id: string | null;
  approved_at: string | null;
  approval_note: string | null;
  rejected_by_user_id: string | null;
  rejected_at: string | null;
  completed_at: string | null;
  created_by: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface TaskCreateInput {
  title: string;
  lead_id: string;
  due_at: string;
  type: TaskType;
  notes?: string | null;
  assigned_user_id?: string | null;
  requires_approval?: boolean;
}

export interface TaskUpdateInput {
  title?: string;
  notes?: string | null;
  due_at?: string;
  status?: TaskStatus;
  assigned_user_id?: string | null;
  version?: number;
}

export async function getTasks(params?: {
  limit?: number;
  offset?: number;
}): Promise<Task[]> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));

  const path = query.toString() ? `/tasks?${query.toString()}` : "/tasks";
  const res = await apiRequest<{ data: Task[] }>(path);
  return res.data;
}

export async function getApprovalQueue(params?: {
  limit?: number;
  offset?: number;
}): Promise<Task[]> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));

  const path = query.toString()
    ? `/tasks/approval-queue?${query.toString()}`
    : "/tasks/approval-queue";
  const res = await apiRequest<{ data: Task[] }>(path);
  return res.data;
}

export async function createTask(payload: TaskCreateInput): Promise<Task> {
  const res = await apiRequest<{ data: Task }>("/tasks", {
    method: "POST",
    body: payload,
    idempotencyKey: createIdempotencyKeyForAction(),
  });
  return res.data;
}

export async function updateTask(
  taskId: string,
  payload: TaskUpdateInput
): Promise<Task> {
  const res = await apiRequest<{ data: Task }>(`/tasks/${taskId}`, {
    method: "PATCH",
    body: payload,
  });
  return res.data;
}

export async function decideTaskApproval(
  taskId: string,
  approved: boolean,
  note?: string | null
): Promise<Task> {
  const endpoint = `/tasks/${taskId}/${approved ? "approve" : "reject"}`;
  const res = await apiRequest<{ data: Task }>(endpoint, {
    method: "POST",
    body: { note: note ?? null },
  });
  return res.data;
}
