import { describe, expect, it } from "vitest";

import { resolveTrendTone } from "@/lib/analytics";

describe("resolveTrendTone", () => {
  it("is unknown when there is no direction (insufficient data)", () => {
    expect(resolveTrendTone(null, true)).toBe("unknown");
  });

  it("is neutral when the trend is flat, regardless of what 'good' means", () => {
    expect(resolveTrendTone("flat", true)).toBe("neutral");
    expect(resolveTrendTone("flat", false)).toBe("neutral");
  });

  it("is positive when increasing is good news and the trend is increasing", () => {
    // e.g. savings trend: increasing is good.
    expect(resolveTrendTone("increasing", true)).toBe("positive");
  });

  it("is negative when increasing is bad news and the trend is increasing", () => {
    // e.g. spending trend: increasing is bad.
    expect(resolveTrendTone("increasing", false)).toBe("negative");
  });

  it("is negative when increasing is good news but the trend is decreasing", () => {
    expect(resolveTrendTone("decreasing", true)).toBe("negative");
  });

  it("is positive when increasing is bad news and the trend is decreasing", () => {
    expect(resolveTrendTone("decreasing", false)).toBe("positive");
  });
});
