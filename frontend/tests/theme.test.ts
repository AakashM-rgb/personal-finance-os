import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  applyTheme,
  isValidThemePreference,
  readStoredTheme,
  resolveIsDark,
  storeTheme,
  THEME_STORAGE_KEY,
} from "@/lib/theme";

function mockPrefersDark(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

describe("isValidThemePreference", () => {
  it("accepts exactly system/light/dark", () => {
    expect(isValidThemePreference("system")).toBe(true);
    expect(isValidThemePreference("light")).toBe(true);
    expect(isValidThemePreference("dark")).toBe(true);
  });

  it("rejects anything else", () => {
    expect(isValidThemePreference("midnight")).toBe(false);
    expect(isValidThemePreference(null)).toBe(false);
    expect(isValidThemePreference(undefined)).toBe(false);
  });
});

describe("resolveIsDark", () => {
  it("dark always resolves true, light always resolves false", () => {
    mockPrefersDark(false);
    expect(resolveIsDark("dark")).toBe(true);
    expect(resolveIsDark("light")).toBe(false);
    mockPrefersDark(true);
    expect(resolveIsDark("dark")).toBe(true);
    expect(resolveIsDark("light")).toBe(false);
  });

  it("system follows the OS-level media query", () => {
    mockPrefersDark(true);
    expect(resolveIsDark("system")).toBe(true);
    mockPrefersDark(false);
    expect(resolveIsDark("system")).toBe(false);
  });
});

describe("applyTheme", () => {
  afterEach(() => {
    document.documentElement.classList.remove("dark");
  });

  it("adds the dark class for dark/system-prefers-dark, removes it otherwise", () => {
    mockPrefersDark(false);
    applyTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    applyTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    mockPrefersDark(true);
    applyTheme("system");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});

describe("readStoredTheme / storeTheme", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("defaults to system when nothing is stored", () => {
    expect(readStoredTheme()).toBe("system");
  });

  it("round-trips a stored value", () => {
    storeTheme("dark");
    expect(readStoredTheme()).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("falls back to system for a corrupted/unexpected stored value", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "not-a-real-theme");
    expect(readStoredTheme()).toBe("system");
  });
});
