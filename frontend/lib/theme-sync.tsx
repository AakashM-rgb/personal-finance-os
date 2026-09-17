"use client";

import { useEffect } from "react";

import { applyTheme, readStoredTheme } from "@/lib/theme";

/**
 * Keeps the applied theme correct after the initial page load:
 *  - re-applies the stored preference once React has mounted (the
 *    beforeInteractive bootstrap script in app/layout.tsx already avoided
 *    the first-paint flash; this is a harmless, cheap confirmation)
 *  - while the stored preference is "system", live-updates the page the
 *    moment the OS-level color scheme changes, without a reload
 */
export function ThemeSync() {
  useEffect(() => {
    applyTheme(readStoredTheme());

    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    function handleChange() {
      if (readStoredTheme() === "system") {
        applyTheme("system");
      }
    }

    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  return null;
}
