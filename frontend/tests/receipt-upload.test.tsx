import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReceiptUpload } from "@/components/receipts/receipt-upload";
import * as receiptsLib from "@/lib/receipts";

function makeFile(name: string, type: string, size: number): File {
  const file = new File(["x".repeat(Math.min(size, 10))], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("ReceiptUpload", () => {
  it("rejects an unsupported file type without calling the API", async () => {
    const uploadSpy = vi.spyOn(receiptsLib, "uploadReceipt");
    const onUploaded = vi.fn();
    render(<ReceiptUpload accessToken="token" onUploaded={onUploaded} />);

    const input = screen.getByLabelText(/upload a receipt/i) as HTMLInputElement;
    const file = makeFile("notes.txt", "text/plain", 100);
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/JPG, PNG, or PDF/));
    expect(uploadSpy).not.toHaveBeenCalled();
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("rejects an oversized file without calling the API", async () => {
    const uploadSpy = vi.spyOn(receiptsLib, "uploadReceipt");
    const onUploaded = vi.fn();
    render(<ReceiptUpload accessToken="token" onUploaded={onUploaded} />);

    const input = screen.getByLabelText(/upload a receipt/i) as HTMLInputElement;
    const file = makeFile("big.png", "image/png", receiptsLib.RECEIPT_MAX_FILE_SIZE_BYTES + 1);
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/smaller/));
    expect(uploadSpy).not.toHaveBeenCalled();
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("uploads a valid file and reports the created receipt", async () => {
    const receipt = { id: "r1" } as receiptsLib.Receipt;
    const uploadSpy = vi.spyOn(receiptsLib, "uploadReceipt").mockResolvedValue(receipt);
    const onUploaded = vi.fn();
    render(<ReceiptUpload accessToken="token" onUploaded={onUploaded} />);

    const input = screen.getByLabelText(/upload a receipt/i) as HTMLInputElement;
    const file = makeFile("receipt.pdf", "application/pdf", 100);
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(receipt));
    expect(uploadSpy).toHaveBeenCalledWith("token", file);
  });
});
