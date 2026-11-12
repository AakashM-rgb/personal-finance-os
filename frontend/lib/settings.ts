import { apiRequest } from "@/lib/api-client";

export type ThemePreference = "system" | "light" | "dark";

/** One boolean per notification category app.services.notification_service
 * (backend) actually generates - kept in sync with
 * backend/app/schemas/user_settings.py's NotificationPreferences. */
export interface NotificationPreferences {
  budget_warnings: boolean;
  payment_reminders: boolean;
  goal_milestones: boolean;
  unusual_spending: boolean;
  recurring_reminders: boolean;
}

export interface UserSettings {
  currency: string;
  theme: ThemePreference;
  ai_enabled: boolean;
  ai_categorization_enabled: boolean;
  notification_preferences: NotificationPreferences;
}

export interface UserSettingsUpdateInput {
  currency?: string;
  theme?: ThemePreference;
  ai_enabled?: boolean;
  ai_categorization_enabled?: boolean;
  notification_preferences?: Partial<NotificationPreferences>;
}

export async function getSettings(accessToken: string): Promise<UserSettings> {
  return apiRequest<UserSettings>("/api/v1/settings", { accessToken });
}

export async function updateSettings(
  accessToken: string,
  input: UserSettingsUpdateInput
): Promise<UserSettings> {
  return apiRequest<UserSettings>("/api/v1/settings", {
    method: "PATCH",
    accessToken,
    body: input,
  });
}
