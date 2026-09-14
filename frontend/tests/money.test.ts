import { describe, expect, it } from "vitest";

import { formatMoney, minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";

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
