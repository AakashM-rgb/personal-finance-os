/**
 * Class-based theme switching, consistent with this project's existing
 * Tailwind v4 setup (see the `@custom-variant dark` line in globals.css) -
 * every `dark:` utility already used across the app keeps working exactly
 * as before, just triggered by a `.dark` class on `<html>` instead of the
 * OS-level `prefers-color-scheme` media query directly.
 *
 * `next-themes` was deliberately not introduced: this is a small, fully
 * self-contained mechanism (one class toggle + one localStorage key) that
 * fits directly into the existing plain-CSS/Tailwind architecture without
 * adding a dependency for something this contained.
 *
 * THEME_STORAGE_KEY's literal value is duplicated in the inline
 * beforeInteractive bootstrap script in app/layout.tsx, which cannot import
 * this module (it runs before any JS bundle loads) - keep both in sync.
 */

export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "finance-app-theme";

function prefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

export function isValidThemePreference(value: unknown): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export function resolveIsDark(theme: ThemePreference): boolean {
  if (theme === "dark") return true;
  if (theme === "light") return false;
  return prefersDark();
}

/** Applies the given preference to the document immediately - safe to call
 * on every render/change, not just once at startup. */
export function applyTheme(theme: ThemePreference): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", resolveIsDark(theme));
}

export function readStoredTheme(): ThemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isValidThemePreference(value) ? value : "system";
  } catch {
    return "system";
  }
}

export function storeTheme(theme: ThemePreference): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Best-effort cache only - applyTheme() already applied it for this page view.
  }
}

/** The exact source of the beforeInteractive script in app/layout.tsx, kept
 * here so the "keep in sync" comment above has one obvious thing to check
 * against. Not imported by the script itself - see the module docstring. */
export const THEME_BOOTSTRAP_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
    var theme = stored === "light" || stored === "dark" || stored === "system" ? stored : "system";
    var isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", isDark);
  } catch (e) {}
})();
`.trim();
