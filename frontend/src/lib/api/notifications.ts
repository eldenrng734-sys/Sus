/**
 * User Notifications API Client.
 *
 * Tenant-scoped and user-scoped: each user only sees and marks their own notifications.
 */

import { apiRequest } from "@/lib/api/client";

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string;
  entity_type: string;
  entity_id: string;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResult {
  notifications: NotificationItem[];
  unread_count: number;
}

export async function getNotifications(params?: {
  read?: boolean;
  limit?: number;
}): Promise<NotificationListResult> {
  const queryParams = new URLSearchParams();
  if (params?.read !== undefined) {
    queryParams.set("read", String(params.read));
  }
  if (params?.limit !== undefined) {
    queryParams.set("limit", String(params.limit));
  }

  const queryStr = queryParams.toString();
  const path = `/notifications${queryStr ? `?${queryStr}` : ""}`;

  const resp = await apiRequest<{
    data: NotificationItem[];
    meta: { unread_count: number };
  }>(path);

  return {
    notifications: resp.data,
    unread_count: resp.meta?.unread_count ?? 0,
  };
}

export async function markNotificationRead(
  id: string
): Promise<NotificationItem> {
  const resp = await apiRequest<{ data: NotificationItem }>(
    `/notifications/${id}/read`,
    {
      method: "PATCH",
    }
  );
  return resp.data;
}

export async function markAllNotificationsRead(): Promise<{ marked_count: number }> {
  const resp = await apiRequest<{ data: { marked_count: number } }>(
    "/notifications/mark-all-read",
    {
      method: "POST",
    }
  );
  return resp.data;
}
