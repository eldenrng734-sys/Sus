import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} from "@/lib/api/notifications";

export function useNotifications(options?: {
  read?: boolean;
  limit?: number;
  refetchInterval?: number;
}) {
  return useQuery({
    queryKey: ["notifications", options?.read, options?.limit],
    queryFn: () =>
      getNotifications({
        read: options?.read,
        limit: options?.limit ?? 20,
      }),
    refetchInterval: options?.refetchInterval ?? 60_000, // Polled every 60s
    refetchOnWindowFocus: true,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => markAllNotificationsRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
