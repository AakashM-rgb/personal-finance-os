import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { endOfLocalDayIso, startOfLocalDayIso, toLocalDateInputValue } from "@/lib/dates";

const originalTz = process.env.TZ;

beforeAll(() => {
  process.env.TZ = "Asia/Kolkata"; // UTC+05:30 - the app's primary audience
});

afterAll(() => {
  process.env.TZ = originalTz;
});

describe("local-day date helpers (IST)", () => {
  it("starts a picked day at local midnight, not UTC midnight", () => {
    expect(startOfLocalDayIso("2026-10-05")).toBe("2026-10-04T18:30:00.000Z");
  });

  it("ends a picked day at the last local millisecond", () => {
    expect(endOfLocalDayIso("2026-10-05")).toBe("2026-10-05T18:29:59.999Z");
  });

  it("includes an expense entered at 01:00 IST in that IST day's range", () => {
    const oneAmIst = new Date("2026-10-04T19:30:00.000Z"); // 5 Oct 01:00 IST
    const from = new Date(startOfLocalDayIso("2026-10-05"));
    const to = new Date(endOfLocalDayIso("2026-10-05"));
    expect(oneAmIst >= from && oneAmIst <= to).toBe(true);
  });

  it("shows a stored bound back as the same local date the user picked", () => {
    expect(toLocalDateInputValue(new Date(startOfLocalDayIso("2026-10-05")))).toBe("2026-10-05");
    expect(toLocalDateInputValue(new Date(endOfLocalDayIso("2026-12-31")))).toBe("2026-12-31");
  });
});
