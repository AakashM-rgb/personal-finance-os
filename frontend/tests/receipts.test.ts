import { describe, expect, it } from "vitest";

import { RECEIPT_MAX_FILE_SIZE_BYTES, validateReceiptFile } from "@/lib/receipts";

describe("validateReceiptFile", () => {
  it("accepts a JPEG within the size limit", () => {
    expect(validateReceiptFile({ type: "image/jpeg", size: 1024 })).toBeNull();
  });

  it("accepts a PNG within the size limit", () => {
    expect(validateReceiptFile({ type: "image/png", size: 1024 })).toBeNull();
  });

  it("accepts a PDF within the size limit", () => {
    expect(validateReceiptFile({ type: "application/pdf", size: 1024 })).toBeNull();
  });

  it("rejects an unsupported file type", () => {
    expect(validateReceiptFile({ type: "text/plain", size: 1024 })).toMatch(/JPG, PNG, or PDF/);
  });

  it("rejects a file over the max size", () => {
    const result = validateReceiptFile({
      type: "application/pdf",
      size: RECEIPT_MAX_FILE_SIZE_BYTES + 1,
    });
    expect(result).toMatch(/smaller/);
  });

  it("accepts a file exactly at the max size", () => {
    expect(
      validateReceiptFile({ type: "application/pdf", size: RECEIPT_MAX_FILE_SIZE_BYTES })
    ).toBeNull();
  });
});
