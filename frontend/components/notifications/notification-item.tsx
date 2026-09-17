"use client";

import type { Notification } from "@/lib/notifications";

const CATEGORY_ICON: Record<Notification["category"], string> = {
  budget_warning: "⚠️",
  budget_exceeded: "🚨",
  subscription_reminder: "🔁",
  credit_card_reminder: "💳",
  goal_milestone: "🎯",
  unusual_spending: "❗",
  recurring_reminder: "📅",
};

function formatDateTime(isoDateTime: string): string {
  return new Date(isoDateTime).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface NotificationItemProps {
  notification: Notification;
  onMarkRead: (id: string) => void;
}

export function NotificationItem({ notification, onMarkRead }: NotificationItemProps) {
  return (
    <li
      className={`flex items-start gap-3 rounded-md border p-3 text-sm ${
        notification.is_read
          ? "border-zinc-100 bg-white dark:border-zinc-900 dark:bg-zinc-950"
          : "border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900"
      }`}
    >
      <span className="text-lg" aria-hidden="true">
        {CATEGORY_ICON[notification.category]}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-medium text-zinc-900 dark:text-zinc-50">{notification.title}</p>
        <p className="mt-0.5 text-zinc-600 dark:text-zinc-400">{notification.message}</p>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
          {formatDateTime(notification.created_at)}
        </p>
      </div>
      {!notification.is_read && (
        <button
          type="button"
          onClick={() => onMarkRead(notification.id)}
          className="shrink-0 whitespace-nowrap text-xs font-medium text-zinc-600 underline hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          Mark read
        </button>
      )}
    </li>
  );
}
