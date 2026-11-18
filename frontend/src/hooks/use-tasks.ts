import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getTasks,
  getApprovalQueue,
  createTask,
  updateTask,
  decideTaskApproval,
  type Task,
  type TaskCreateInput,
  type TaskUpdateInput,
} from "@/lib/api/tasks";

export function getTenantTodayString(timezone: string): string {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone || "Asia/Dhaka",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  } catch {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Dhaka",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  }
}

export function getTenantDateString(
  isoString: string,
  timezone: string
): string {
  try {
    const date = new Date(isoString);
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone || "Asia/Dhaka",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  } catch {
    return isoString.slice(0, 10);
  }
}

export function getTaskDayBucket(
  task: Task,
  timezone: string
): "today" | "overdue" | "upcoming" {
  const today = getTenantTodayString(timezone);
  const taskDay = getTenantDateString(task.due_at, timezone);

  if (taskDay < today) {
    return "overdue";
  }
  if (taskDay === today) {
    return "today";
  }
  return "upcoming";
}

export function formatTenantDateTime(
  isoString: string,
  timezone: string
): string {
  try {
    const date = new Date(isoString);
    return new Intl.DateTimeFormat("en-US", {
      timeZone: timezone || "Asia/Dhaka",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).format(date);
  } catch {
    return new Date(isoString).toLocaleDateString();
  }
}

export function useTasks(options?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ["tasks", options?.limit, options?.offset],
    queryFn: () => getTasks(options),
  });
}

export function useApprovalQueue(options?: {
  enabled?: boolean;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: ["approval-queue", options?.limit, options?.offset],
    queryFn: () => getApprovalQueue(options),
    enabled: options?.enabled ?? true,
    retry: false, // Don't retry on 403 for non-managers
  });
}

export function useCreateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: TaskCreateInput) => createTask(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["approval-queue"] });
    },
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      taskId,
      payload,
    }: {
      taskId: string;
      payload: TaskUpdateInput;
    }) => updateTask(taskId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["approval-queue"] });
    },
  });
}

export function useDecideApproval() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      taskId,
      approved,
      note,
    }: {
      taskId: string;
      approved: boolean;
      note?: string | null;
    }) => decideTaskApproval(taskId, approved, note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["approval-queue"] });
    },
  });
}
