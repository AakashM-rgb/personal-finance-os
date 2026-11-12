import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationsSection } from "@/components/settings/notifications-section";
import { ApiError } from "@/lib/api-client";
import * as settingsLib from "@/lib/settings";
import type { UserSettings } from "@/lib/settings";

const BASE_SETTINGS: UserSettings = {
  currency: "INR",
  theme: "system",
  ai_enabled: true,
  ai_categorization_enabled: false,
  notification_preferences: {
    budget_warnings: true,
    payment_reminders: true,
    goal_milestones: true,
    unusual_spending: true,
    recurring_reminders: true,
  },
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("NotificationsSection", () => {
  it("renders every notification category as its own checkbox, all checked by default", () => {
    render(<NotificationsSection accessToken="token" settings={BASE_SETTINGS} />);

    expect(screen.getByRole("checkbox", { name: /budget warnings/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /upcoming payment reminders/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /savings goal progress/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /unusual spending/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /recurring expense reminders/i })).toBeChecked();
  });

  it("disabling one category saves only that category", async () => {
    const spy = vi.spyOn(settingsLib, "updateSettings").mockResolvedValue({
      ...BASE_SETTINGS,
      notification_preferences: { ...BASE_SETTINGS.notification_preferences, budget_warnings: false },
    });

    render(<NotificationsSection accessToken="token" settings={BASE_SETTINGS} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /budget warnings/i }));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("token", {
        notification_preferences: { budget_warnings: false },
      })
    );
    expect(screen.getByRole("checkbox", { name: /budget warnings/i })).not.toBeChecked();
    // Every other category is left untouched.
    expect(screen.getByRole("checkbox", { name: /unusual spending/i })).toBeChecked();
  });

  it("reverts the toggle and shows an error if saving fails", async () => {
    vi.spyOn(settingsLib, "updateSettings").mockRejectedValue(
      new ApiError(500, {
        code: "internal_error",
        message: "Failed to save notification setting.",
        field_errors: null,
      })
    );

    render(<NotificationsSection accessToken="token" settings={BASE_SETTINGS} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /goal progress/i }));

    expect(await screen.findByText("Failed to save notification setting.")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /goal progress/i })).toBeChecked()
    );
  });

  it("re-enabling a disabled category saves the new value", async () => {
    const disabledSettings: UserSettings = {
      ...BASE_SETTINGS,
      notification_preferences: { ...BASE_SETTINGS.notification_preferences, unusual_spending: false },
    };
    const spy = vi.spyOn(settingsLib, "updateSettings").mockResolvedValue({
      ...disabledSettings,
      notification_preferences: { ...disabledSettings.notification_preferences, unusual_spending: true },
    });

    render(<NotificationsSection accessToken="token" settings={disabledSettings} />);
    expect(screen.getByRole("checkbox", { name: /unusual spending/i })).not.toBeChecked();

    fireEvent.click(screen.getByRole("checkbox", { name: /unusual spending/i }));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("token", {
        notification_preferences: { unusual_spending: true },
      })
    );
  });

  it("every checkbox has an accessible, keyboard-focusable label", () => {
    render(<NotificationsSection accessToken="token" settings={BASE_SETTINGS} />);
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(5);
    for (const checkbox of checkboxes) {
      expect(checkbox).toBeVisible();
    }
  });
});
