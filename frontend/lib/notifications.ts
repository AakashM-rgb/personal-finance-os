import { apiRequest, apiRequestWithMeta } from "@/lib/api-client";

export type NotificationCategory =
  | "budget_warning"
  | "budget_exceeded"
  | "subscription_reminder"
  | "credit_card_reminder"
  | "goal_milestone"
  | "unusual_spending"
  | "recurring_reminder";

export interface Notification {
  id: string;
  category: NotificationCategory;
  title: string;
  message: string;
  reference_type: string | null;
  reference_id: string | null;
  action_url: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResult {
  notifications: Notification[];
  total: number;
}

export async function listNotifications(
  accessToken: string,
  options: { unreadOnly?: boolean; limit?: number; offset?: number } = {}
): Promise<NotificationListResult> {
  const params = new URLSearchParams();
  if (options.unreadOnly) params.set("unread_only", "true");
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  const query = params.toString();

  const { data, meta } = await apiRequestWithMeta<Notification[]>(
    `/api/v1/notifications${query ? `?${query}` : ""}`,
    { accessToken }
  );
  return { notifications: data, total: (meta?.total as number) ?? data.length };
}

export async function getUnreadCount(accessToken: string): Promise<number> {
  const { unread_count } = await apiRequest<{ unread_count: number }>(
    "/api/v1/notifications/unread-count",
    { accessToken }
  );
  return unread_count;
}

export async function markNotificationRead(
  accessToken: string,
  notificationId: string
): Promise<Notification> {
  return apiRequest<Notification>(`/api/v1/notifications/${notificationId}/read`, {
    method: "PUT",
    accessToken,
  });
}

export async function markAllNotificationsRead(
  accessToken: string
): Promise<{ updated_count: number }> {
  return apiRequest<{ updated_count: number }>("/api/v1/notifications/read-all", {
    method: "POST",
    accessToken,
  });
}
