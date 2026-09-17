import { apiRequest } from "@/lib/api-client";

export type ThemePreference = "system" | "light" | "dark";

export interface UserSettings {
  currency: string;
  theme: ThemePreference;
  ai_enabled: boolean;
}

export interface UserSettingsUpdateInput {
  currency?: string;
  theme?: ThemePreference;
  ai_enabled?: boolean;
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
