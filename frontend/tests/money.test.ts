import { describe, expect, it } from "vitest";

import {
  formatMoney,
  MAX_MONEY_MINOR,
  minorUnitsToInputValue,
  parseMoneyToMinorUnits,
} from "@/lib/money";

describe("formatMoney", () => {
  it("formats INR minor units with two decimal places", () => {
    expect(formatMoney(3245000, "INR")).toBe("₹32,450.00");
  });

  it("formats JPY with no decimal places", () => {
    expect(formatMoney(1500, "JPY")).toBe("¥1,500");
  });

  it("formats zero and negative amounts", () => {
    expect(formatMoney(0, "INR")).toBe("₹0.00");
    expect(formatMoney(-500, "INR")).toBe("-₹5.00");
  });
});

describe("minorUnitsToInputValue", () => {
  it("converts minor units to a plain decimal string", () => {
    expect(minorUnitsToInputValue(3245000, "INR")).toBe("32450.00");
    expect(minorUnitsToInputValue(5, "INR")).toBe("0.05");
    expect(minorUnitsToInputValue(0, "INR")).toBe("0.00");
  });

  it("handles negative amounts without breaking the sign placement", () => {
    expect(minorUnitsToInputValue(-500, "INR")).toBe("-5.00");
  });

  it("does not add a decimal point for zero-decimal currencies", () => {
    expect(minorUnitsToInputValue(1500, "JPY")).toBe("1500");
  });
});

describe("parseMoneyToMinorUnits", () => {
  it("parses a plain decimal amount", () => {
    expect(parseMoneyToMinorUnits("32450.00", "INR")).toBe(3245000);
  });

  it("strips thousands separators", () => {
    expect(parseMoneyToMinorUnits("32,450.5", "INR")).toBe(3245050);
  });

  it("pads a single decimal digit", () => {
    expect(parseMoneyToMinorUnits("10.5", "INR")).toBe(1050);
  });

  it("handles whole numbers with no decimal point", () => {
    expect(parseMoneyToMinorUnits("500", "INR")).toBe(50000);
  });

  it("handles negative amounts", () => {
    expect(parseMoneyToMinorUnits("-5.00", "INR")).toBe(-500);
  });

  it("returns null for invalid input", () => {
    expect(parseMoneyToMinorUnits("not a number", "INR")).toBeNull();
    expect(parseMoneyToMinorUnits("", "INR")).toBeNull();
    expect(parseMoneyToMinorUnits("12.999", "INR")).toBeNull(); // too many decimals
  });

  it("round-trips through minorUnitsToInputValue", () => {
    const original = 987654;
    const asString = minorUnitsToInputValue(original, "INR");
    expect(parseMoneyToMinorUnits(asString, "INR")).toBe(original);
  });

  it("treats JPY as a zero-decimal currency", () => {
    expect(parseMoneyToMinorUnits("1500", "JPY")).toBe(1500);
    expect(parseMoneyToMinorUnits("15.5", "JPY")).toBeNull();
  });
});

// F-006, client side: an amount too large to represent exactly must never be
// silently turned into a different number and sent to the API.
describe("parseMoneyToMinorUnits bounds", () => {
  it("accepts the largest amount the API allows", () => {
    expect(parseMoneyToMinorUnits("100000000000.00")).toBe(MAX_MONEY_MINOR);
  });

  it("rejects an amount above the API's ceiling", () => {
    expect(parseMoneyToMinorUnits("100000000000.01")).toBeNull();
    expect(parseMoneyToMinorUnits("999999999999999")).toBeNull();
  });

  it("rejects a magnitude that cannot be represented exactly", () => {
    // parseInt would return 1e20 here - a different number than was typed.
    expect(parseMoneyToMinorUnits("99999999999999999999")).toBeNull();
  });

  it("applies the same ceiling to negative amounts", () => {
    expect(parseMoneyToMinorUnits("-100000000000.00")).toBe(-MAX_MONEY_MINOR);
    expect(parseMoneyToMinorUnits("-100000000000.01")).toBeNull();
  });

  it("applies the ceiling to zero-decimal currencies too", () => {
    expect(parseMoneyToMinorUnits(String(MAX_MONEY_MINOR), "JPY")).toBe(MAX_MONEY_MINOR);
    expect(parseMoneyToMinorUnits(String(MAX_MONEY_MINOR + 1), "JPY")).toBeNull();
  });

  it("still accepts ordinary amounts unchanged", () => {
    expect(parseMoneyToMinorUnits("1,234.5")).toBe(123450);
    expect(parseMoneyToMinorUnits("0.01")).toBe(1);
  });

  it("matches the backend's MAX_MONEY_MINOR", () => {
    expect(MAX_MONEY_MINOR).toBe(10 ** 13);
  });
});
