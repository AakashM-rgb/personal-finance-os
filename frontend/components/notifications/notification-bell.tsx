"use client";

import { useEffect, useState } from "react";

import { NotificationItem } from "@/components/notifications/notification-item";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type Notification,
} from "@/lib/notifications";

interface NotificationBellProps {
  accessToken: string;
}

/** The unread badge count is fetched independently of the panel being
 * open - a user should see they have something waiting without first
 * opening it. Opening the panel fetches the actual list, which also
 * regenerates due notifications server-side (see
 * app.api.v1.notifications), so it's always current. */
export function NotificationBell({ accessToken }: NotificationBellProps) {
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isMarkingAll, setIsMarkingAll] = useState(false);

  useEffect(() => {
    let isMounted = true;
    void getUnreadCount(accessToken)
      .then((count) => {
        if (isMounted) setUnreadCount(count);
      })
      .catch(() => {
        // The badge is a convenience, not a critical control - a failed
        // background count fetch fails silently rather than surfacing an
        // error the user never asked to see.
      });
    return () => {
      isMounted = false;
    };
  }, [accessToken]);

  function loadNotifications() {
    setError(null);
    setNotifications(null);
    listNotifications(accessToken, { limit: 50 })
      .then((result) => {
        setNotifications(result.notifications);
        setUnreadCount(result.notifications.filter((n) => !n.is_read).length);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Failed to load notifications.");
      });
  }

  function handleOpen() {
    setIsOpen(true);
    loadNotifications();
  }

  async function handleMarkRead(id: string) {
    if (!notifications) return;
    const previous = notifications;
    setNotifications(
      notifications.map((n) => (n.id === id ? { ...n, is_read: true } : n))
    );
    setUnreadCount((count) => Math.max(count - 1, 0));
    try {
      await markNotificationRead(accessToken, id);
    } catch {
      setNotifications(previous);
      setUnreadCount((count) => count + 1);
    }
  }

  async function handleMarkAllRead() {
    if (!notifications) return;
    const previous = notifications;
    const previousUnread = unreadCount;
    setIsMarkingAll(true);
    setNotifications(notifications.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
    try {
      await markAllNotificationsRead(accessToken);
    } catch (err) {
      setNotifications(previous);
      setUnreadCount(previousUnread);
      setError(err instanceof ApiError ? err.message : "Failed to mark all as read.");
    } finally {
      setIsMarkingAll(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={handleOpen}
        aria-label={
          unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"
        }
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
      >
        <span aria-hidden="true" className="text-lg">
          🔔
        </span>
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            className="absolute top-0.5 right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-medium text-white"
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <Modal title="Notifications" onClose={() => setIsOpen(false)}>
          <div className="flex max-h-[70vh] flex-col gap-3">
            {error && (
              <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
                {error}{" "}
                <button type="button" onClick={loadNotifications} className="font-medium underline">
                  Try again
                </button>
              </div>
            )}

            {notifications === null && !error && (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-16" />
                <Skeleton className="h-16" />
                <Skeleton className="h-16" />
              </div>
            )}

            {notifications !== null && notifications.length === 0 && (
              <p className="py-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
                You&apos;re all caught up - no notifications right now.
              </p>
            )}

            {notifications !== null && notifications.length > 0 && (
              <>
                <div className="flex justify-end">
                  <Button
                    variant="secondary"
                    onClick={() => void handleMarkAllRead()}
                    disabled={isMarkingAll || unreadCount === 0}
                  >
                    Mark all as read
                  </Button>
                </div>
                <ul className="flex flex-col gap-2 overflow-y-auto">
                  {notifications.map((notification) => (
                    <NotificationItem
                      key={notification.id}
                      notification={notification}
                      onMarkRead={(id) => void handleMarkRead(id)}
                    />
                  ))}
                </ul>
              </>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
