import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PreferencesSection } from "@/components/settings/preferences-section";
import { ApiError } from "@/lib/api-client";
import * as settingsLib from "@/lib/settings";

const BASE_SETTINGS = {
  currency: "INR",
  theme: "system" as const,
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
  document.documentElement.classList.remove("dark");
  window.localStorage.clear();
});

describe("PreferencesSection", () => {
  it("saves a currency change immediately", async () => {
    const spy = vi
      .spyOn(settingsLib, "updateSettings")
      .mockResolvedValue({ ...BASE_SETTINGS, currency: "USD" });

    render(<PreferencesSection accessToken="token" settings={BASE_SETTINGS} />);
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USD" } });

    await waitFor(() => expect(spy).toHaveBeenCalledWith("token", { currency: "USD" }));
    expect(screen.getByLabelText("Currency")).toHaveValue("USD");
  });

  it("reverts the currency and shows an error if saving fails", async () => {
    vi.spyOn(settingsLib, "updateSettings").mockRejectedValue(
      new ApiError(422, {
        code: "validation_error",
        message: "currency must be one of the supported list",
        field_errors: null,
      })
    );

    render(<PreferencesSection accessToken="token" settings={BASE_SETTINGS} />);
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USD" } });

    expect(await screen.findByText("currency must be one of the supported list")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Currency")).toHaveValue("INR"));
  });

  it("applies the theme to the document immediately on change", async () => {
    vi.spyOn(settingsLib, "updateSettings").mockResolvedValue({ ...BASE_SETTINGS, theme: "dark" });

    render(<PreferencesSection accessToken="token" settings={BASE_SETTINGS} />);
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });

    // Applied synchronously, before the PATCH call even resolves.
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("finance-app-theme")).toBe("dark");
    await waitFor(() =>
      expect(settingsLib.updateSettings).toHaveBeenCalledWith("token", { theme: "dark" })
    );
  });

  it("reverts the applied theme if saving fails", async () => {
    vi.spyOn(settingsLib, "updateSettings").mockRejectedValue(
      new ApiError(422, { code: "validation_error", message: "Invalid theme.", field_errors: null })
    );

    render(<PreferencesSection accessToken="token" settings={BASE_SETTINGS} />);
    fireEvent.change(screen.getByLabelText("Theme"), { target: { value: "dark" } });

    expect(await screen.findByText("Invalid theme.")).toBeInTheDocument();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(screen.getByLabelText("Theme")).toHaveValue("system");
  });

  it("toggles the AI-enabled checkbox and saves it", async () => {
    const spy = vi
      .spyOn(settingsLib, "updateSettings")
      .mockResolvedValue({ ...BASE_SETTINGS, ai_enabled: false });

    render(<PreferencesSection accessToken="token" settings={BASE_SETTINGS} />);
    const checkbox = screen.getByRole("checkbox", {
      name: "Allow the AI assistant to access my financial data",
    });
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);

    await waitFor(() => expect(spy).toHaveBeenCalledWith("token", { ai_enabled: false }));
    expect(checkbox).not.toBeChecked();
  });

  it("renders the AI-categorization checkbox unchecked by default", () => {
    render(<PreferencesSection accessToken="token" settings={BASE_SETTINGS} />);
    const checkbox = screen.getByRole("checkbox", {
      name: "Let AI suggest categories for synced transactions",
    });
    expect(checkbox).not.toBeChecked();
  });

  it("toggles the AI-categorization checkbox and saves only that field", async () => {
    const spy = vi
      .spyOn(settingsLib, "updateSettings")
      .mockResolvedValue({ ...BASE_SETTINGS, ai_categorization_enabled: true });

    render(<PreferencesSection accessToken="token" settings={BASE_SETTINGS} />);
    const checkbox = screen.getByRole("checkbox", {
      name: "Let AI suggest categories for synced transactions",
    });
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("token", { ai_categorization_enabled: true })
    );
    expect(spy).toHaveBeenCalledTimes(1);
    expect(checkbox).toBeChecked();

    // Independent of the AI-assistant checkbox - unaffected by this save.
    expect(
      screen.getByRole("checkbox", { name: "Allow the AI assistant to access my financial data" })
    ).toBeChecked();
  });

  it("reverts the AI-categorization checkbox and shows an error if saving fails", async () => {
    vi.spyOn(settingsLib, "updateSettings").mockRejectedValue(
      new ApiError(422, {
        code: "validation_error",
        message: "Failed to save AI categorization setting.",
        field_errors: null,
      })
    );

    render(<PreferencesSection accessToken="token" settings={BASE_SETTINGS} />);
    const checkbox = screen.getByRole("checkbox", {
      name: "Let AI suggest categories for synced transactions",
    });

    fireEvent.click(checkbox);

    expect(
      await screen.findByText("Failed to save AI categorization setting.")
    ).toBeInTheDocument();
    await waitFor(() => expect(checkbox).not.toBeChecked());
  });
});
