import { describe, expect, it } from "vitest";

import manifest from "@/app/manifest";

describe("PWA manifest", () => {
  const result = manifest();

  it("declares a name and short_name", () => {
    expect(result.name).toBeTruthy();
    expect(result.short_name).toBeTruthy();
    expect(result.short_name!.length).toBeLessThanOrEqual(30); // stays legible under a home-screen icon
  });

  it("uses the standalone display mode (installable app, not a bare browser tab)", () => {
    expect(result.display).toBe("standalone");
  });

  it("declares a start_url within the app", () => {
    expect(result.start_url).toBe("/dashboard");
  });

  it("declares theme_color and background_color", () => {
    expect(result.theme_color).toMatch(/^#[0-9a-f]{6}$/i);
    expect(result.background_color).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it("declares at least one icon, including a maskable one", () => {
    expect(result.icons?.length).toBeGreaterThan(0);
    const hasMaskable = result.icons?.some((icon) => icon.purpose === "maskable");
    expect(hasMaskable).toBe(true);
  });

  it("never embeds a secret-shaped value anywhere in the manifest", () => {
    const text = JSON.stringify(result).toLowerCase();
    for (const forbidden of ["api_key", "apikey", "secret", "token", "password", "bearer "]) {
      expect(text).not.toContain(forbidden);
    }
  });
});
