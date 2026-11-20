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
import {
  getTenantTodayString,
  getTenantDateString,
} from "@/lib/format";

// Re-export so existing imports from "@/hooks/use-tasks" keep working.
export { formatTenantDateTime, getTenantTodayString, getTenantDateString } from "@/lib/format";

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
