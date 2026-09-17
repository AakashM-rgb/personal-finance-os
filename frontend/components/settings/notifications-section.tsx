"use client";

import { useState } from "react";

import { Card } from "@/components/ui/card";
import { FormError } from "@/components/ui/form-error";
import { ApiError } from "@/lib/api-client";
import {
  updateSettings,
  type NotificationPreferences,
  type UserSettings,
} from "@/lib/settings";

const CATEGORY_LABELS: { key: keyof NotificationPreferences; label: string; hint: string }[] = [
  {
    key: "budget_warnings",
    label: "Budget warnings",
    hint: "When a budget reaches its warning threshold or is exceeded.",
  },
  {
    key: "payment_reminders",
    label: "Upcoming payment reminders",
    hint: "Subscription renewals and credit-card payments due soon.",
  },
  {
    key: "goal_milestones",
    label: "Savings goal progress",
    hint: "When a savings goal reaches 25%, 50%, 75%, or 100% funded.",
  },
  {
    key: "unusual_spending",
    label: "Unusual spending",
    hint: "A transaction well above your usual spending in that category.",
  },
  {
    key: "recurring_reminders",
    label: "Recurring expense reminders",
    hint: "An active recurring expense due soon.",
  },
];

interface NotificationsSectionProps {
  accessToken: string;
  settings: UserSettings;
}

/** Each category saves independently the moment it's toggled - the same
 * optimistic-update-with-revert-on-failure pattern as PreferencesSection's
 * ai_enabled toggle, applied per category here. */
export function NotificationsSection({ accessToken, settings }: NotificationsSectionProps) {
  const [preferences, setPreferences] = useState<NotificationPreferences>(
    settings.notification_preferences
  );
  const [savingKey, setSavingKey] = useState<keyof NotificationPreferences | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleToggle(key: keyof NotificationPreferences, checked: boolean) {
    const previous = preferences;
    setPreferences({ ...preferences, [key]: checked });
    setError(null);
    setSavingKey(key);
    try {
      const updated = await updateSettings(accessToken, {
        notification_preferences: { [key]: checked },
      });
      setPreferences(updated.notification_preferences);
    } catch (err) {
      setPreferences(previous);
      setError(err instanceof ApiError ? err.message : "Failed to save notification setting.");
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Notifications</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Choose which notifications you want to receive. Every notification is generated from
          your own real account data - never fabricated.
        </p>
      </div>

      <ul className="flex flex-col gap-4">
        {CATEGORY_LABELS.map(({ key, label, hint }) => (
          <li key={key} className="flex flex-col gap-1">
            <label className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
              <input
                type="checkbox"
                checked={preferences[key]}
                onChange={(e) => void handleToggle(key, e.target.checked)}
                disabled={savingKey === key}
              />
              {label}
            </label>
            <p className="pl-6 text-xs text-zinc-500 dark:text-zinc-400">{hint}</p>
          </li>
        ))}
      </ul>

      <FormError message={error} />
    </Card>
  );
}
