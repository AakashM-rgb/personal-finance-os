"use client";

import { useState } from "react";

import { Card } from "@/components/ui/card";
import { FormError } from "@/components/ui/form-error";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import { CURRENCIES } from "@/lib/money";
import { updateSettings, type ThemePreference, type UserSettings } from "@/lib/settings";
import { applyTheme, isValidThemePreference, storeTheme } from "@/lib/theme";

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

interface PreferencesSectionProps {
  accessToken: string;
  settings: UserSettings;
}

/**
 * Each preference saves independently the moment it changes - these are
 * unrelated toggles, not one multi-field record, so there is no
 * "unsaved changes" state to batch behind a single Save button. Every
 * change is optimistic and reverts itself (including, for theme, undoing
 * the already-applied visual change) if the PATCH fails.
 */
export function PreferencesSection({ accessToken, settings }: PreferencesSectionProps) {
  const [currency, setCurrency] = useState(settings.currency);
  const [currencyError, setCurrencyError] = useState<string | null>(null);
  const [isSavingCurrency, setIsSavingCurrency] = useState(false);

  const [theme, setTheme] = useState<ThemePreference>(settings.theme);
  const [themeError, setThemeError] = useState<string | null>(null);
  const [isSavingTheme, setIsSavingTheme] = useState(false);

  const [aiEnabled, setAiEnabled] = useState(settings.ai_enabled);
  const [aiError, setAiError] = useState<string | null>(null);
  const [isSavingAi, setIsSavingAi] = useState(false);

  const [aiCategorizationEnabled, setAiCategorizationEnabled] = useState(
    settings.ai_categorization_enabled
  );
  const [aiCategorizationError, setAiCategorizationError] = useState<string | null>(null);
  const [isSavingAiCategorization, setIsSavingAiCategorization] = useState(false);

  async function handleCurrencyChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const previous = currency;
    const next = event.target.value;
    setCurrency(next);
    setCurrencyError(null);
    setIsSavingCurrency(true);
    try {
      await updateSettings(accessToken, { currency: next });
    } catch (err) {
      setCurrency(previous);
      setCurrencyError(err instanceof ApiError ? err.message : "Failed to save currency.");
    } finally {
      setIsSavingCurrency(false);
    }
  }

  async function handleThemeChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const previous = theme;
    const next = event.target.value;
    if (!isValidThemePreference(next)) return;

    setTheme(next);
    setThemeError(null);
    setIsSavingTheme(true);
    // Apply immediately - the user should see the effect before the network
    // call even resolves, not after.
    applyTheme(next);
    storeTheme(next);
    try {
      await updateSettings(accessToken, { theme: next });
    } catch (err) {
      setTheme(previous);
      applyTheme(previous);
      storeTheme(previous);
      setThemeError(err instanceof ApiError ? err.message : "Failed to save theme.");
    } finally {
      setIsSavingTheme(false);
    }
  }

  async function handleAiToggle(event: React.ChangeEvent<HTMLInputElement>) {
    const previous = aiEnabled;
    const next = event.target.checked;
    setAiEnabled(next);
    setAiError(null);
    setIsSavingAi(true);
    try {
      await updateSettings(accessToken, { ai_enabled: next });
    } catch (err) {
      setAiEnabled(previous);
      setAiError(err instanceof ApiError ? err.message : "Failed to save AI setting.");
    } finally {
      setIsSavingAi(false);
    }
  }

  async function handleAiCategorizationToggle(event: React.ChangeEvent<HTMLInputElement>) {
    const previous = aiCategorizationEnabled;
    const next = event.target.checked;
    setAiCategorizationEnabled(next);
    setAiCategorizationError(null);
    setIsSavingAiCategorization(true);
    try {
      await updateSettings(accessToken, { ai_categorization_enabled: next });
    } catch (err) {
      setAiCategorizationEnabled(previous);
      setAiCategorizationError(
        err instanceof ApiError ? err.message : "Failed to save AI categorization setting."
      );
    } finally {
      setIsSavingAiCategorization(false);
    }
  }

  return (
    <Card className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Preferences</h2>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="settings-currency">Currency</Label>
        <Select
          id="settings-currency"
          className="max-w-xs"
          value={currency}
          onChange={(e) => void handleCurrencyChange(e)}
          disabled={isSavingCurrency}
        >
          {CURRENCIES.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </Select>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Used across your dashboard, budgets, and reports as your base currency.
        </p>
        <FormError message={currencyError} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="settings-theme">Theme</Label>
        <Select
          id="settings-theme"
          className="max-w-xs"
          value={theme}
          onChange={(e) => void handleThemeChange(e)}
          disabled={isSavingTheme}
        >
          {THEME_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          System follows your device&apos;s light/dark setting automatically.
        </p>
        <FormError message={themeError} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          <input
            type="checkbox"
            checked={aiEnabled}
            onChange={(e) => void handleAiToggle(e)}
            disabled={isSavingAi}
          />
          Allow the AI assistant to access my financial data
        </label>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          When turned off, the assistant and natural-language search can no longer read your
          transactions, budgets, or goals.
        </p>
        <FormError message={aiError} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          <input
            type="checkbox"
            checked={aiCategorizationEnabled}
            onChange={(e) => void handleAiCategorizationToggle(e)}
            disabled={isSavingAiCategorization}
          />
          Let AI suggest categories for synced transactions
        </label>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          When enabled, transactions your bank sync can&apos;t categorize automatically may be
          sent to an AI provider to suggest a category. Off by default, and separate from the AI
          assistant setting above - your own merchant rules always take priority.
        </p>
        <FormError message={aiCategorizationError} />
      </div>
    </Card>
  );
}
