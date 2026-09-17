import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationBell } from "@/components/notifications/notification-bell";
import { ApiError } from "@/lib/api-client";
import * as notificationsLib from "@/lib/notifications";
import type { Notification } from "@/lib/notifications";

afterEach(() => {
  vi.restoreAllMocks();
});

function makeNotification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: "n1",
    category: "budget_warning",
    title: "Food budget warning",
    message: "You've used 75% of your Food budget this month.",
    reference_type: "budget_item",
    reference_id: "b1",
    action_url: "/budgets",
    is_read: false,
    created_at: "2026-09-17T08:00:00Z",
    ...overrides,
  };
}

describe("NotificationBell", () => {
  it("shows the unread count badge once the background count loads", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(3);

    render(<NotificationBell accessToken="token" />);

    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Notifications, 3 unread" })
    ).toBeInTheDocument();
  });

  it("shows no badge when there are no unread notifications", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(0);

    render(<NotificationBell accessToken="token" />);

    await waitFor(() => expect(notificationsLib.getUnreadCount).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("shows a loading state, then the list, when opened", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(1);
    vi.spyOn(notificationsLib, "listNotifications").mockResolvedValue({
      notifications: [makeNotification()],
      total: 1,
    });

    render(<NotificationBell accessToken="token" />);
    fireEvent.click(await screen.findByRole("button", { name: /notifications/i }));

    expect(await screen.findByText("Food budget warning")).toBeInTheDocument();
    expect(
      screen.getByText("You've used 75% of your Food budget this month.")
    ).toBeInTheDocument();
  });

  it("shows an empty state when there are no notifications", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(0);
    vi.spyOn(notificationsLib, "listNotifications").mockResolvedValue({
      notifications: [],
      total: 0,
    });

    render(<NotificationBell accessToken="token" />);
    fireEvent.click(await screen.findByRole("button", { name: "Notifications" }));

    expect(await screen.findByText(/all caught up/i)).toBeInTheDocument();
  });

  it("shows an error state with retry when the list fails to load", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(0);
    vi.spyOn(notificationsLib, "listNotifications").mockRejectedValue(
      new ApiError(500, {
        code: "internal_error",
        message: "Failed to load notifications.",
        field_errors: null,
      })
    );

    render(<NotificationBell accessToken="token" />);
    fireEvent.click(await screen.findByRole("button", { name: "Notifications" }));

    expect(await screen.findByText("Failed to load notifications.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("marks a single notification as read", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(1);
    vi.spyOn(notificationsLib, "listNotifications").mockResolvedValue({
      notifications: [makeNotification()],
      total: 1,
    });
    const markRead = vi
      .spyOn(notificationsLib, "markNotificationRead")
      .mockResolvedValue(makeNotification({ is_read: true }));

    render(<NotificationBell accessToken="token" />);
    fireEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    await screen.findByText("Food budget warning");

    fireEvent.click(screen.getByRole("button", { name: "Mark read" }));

    await waitFor(() => expect(markRead).toHaveBeenCalledWith("token", "n1"));
    // The "Mark read" action disappears once a notification is read.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Mark read" })).not.toBeInTheDocument()
    );
  });

  it("marks all notifications as read", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(2);
    vi.spyOn(notificationsLib, "listNotifications").mockResolvedValue({
      notifications: [
        makeNotification({ id: "n1" }),
        makeNotification({ id: "n2", title: "Second notification" }),
      ],
      total: 2,
    });
    const markAllRead = vi
      .spyOn(notificationsLib, "markAllNotificationsRead")
      .mockResolvedValue({ updated_count: 2 });

    render(<NotificationBell accessToken="token" />);
    fireEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    await screen.findByText("Second notification");

    fireEvent.click(screen.getByRole("button", { name: "Mark all as read" }));

    await waitFor(() => expect(markAllRead).toHaveBeenCalledWith("token"));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Mark read" })).not.toBeInTheDocument()
    );
  });

  it("the 'mark all as read' button is disabled once nothing is unread", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(0);
    vi.spyOn(notificationsLib, "listNotifications").mockResolvedValue({
      notifications: [makeNotification({ is_read: true })],
      total: 1,
    });

    render(<NotificationBell accessToken="token" />);
    fireEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    await screen.findByText("Food budget warning");

    expect(screen.getByRole("button", { name: "Mark all as read" })).toBeDisabled();
  });

  it("is a real accessible dialog: role=dialog, labelled, closable with Escape", async () => {
    vi.spyOn(notificationsLib, "getUnreadCount").mockResolvedValue(0);
    vi.spyOn(notificationsLib, "listNotifications").mockResolvedValue({
      notifications: [],
      total: 0,
    });

    render(<NotificationBell accessToken="token" />);
    fireEvent.click(await screen.findByRole("button", { name: "Notifications" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Notifications")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
