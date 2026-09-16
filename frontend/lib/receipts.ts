import { apiFetchBlob, apiRequest, apiUpload } from "@/lib/api-client";
import type { Transaction } from "@/lib/transactions";

// Kept in sync with backend/app/schemas/receipt.py::RECEIPT_MAX_FILE_SIZE_BYTES -
// used only to reject an oversized file before spending an upload; the
// backend re-validates this independently and is the actual authority.
export const RECEIPT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

export const RECEIPT_ACCEPTED_CONTENT_TYPES = ["image/jpeg", "image/png", "application/pdf"];

/**
 * Client-side pre-check only, mirroring backend/app/services/receipt_service.py's
 * validation - a UX convenience that saves a doomed upload, never a substitute
 * for the backend's own re-validation (which sniffs real file bytes and is the
 * actual authority; see CLAUDE.md "client-side validation is a UX convenience").
 */
export function validateReceiptFile(file: { type: string; size: number }): string | null {
  if (!RECEIPT_ACCEPTED_CONTENT_TYPES.includes(file.type)) {
    return "Upload a JPG, PNG, or PDF file.";
  }
  if (file.size > RECEIPT_MAX_FILE_SIZE_BYTES) {
    return `Files must be ${RECEIPT_MAX_FILE_SIZE_BYTES / (1024 * 1024)}MB or smaller.`;
  }
  return null;
}

export type ReceiptStatus = "pending" | "processed" | "confirmed" | "failed";

export interface ReceiptItem {
  description: string;
  quantity: string | null;
  unit_price_minor: number | null;
  line_total_minor: number | null;
}

export interface ReceiptExtraction {
  provider: string | null;
  confidence: number | null;
  processed_at: string | null;
  error: string | null;

  merchant: string | null;
  date: string | null;
  total_minor: number | null;
  tax_minor: number | null;
  items: ReceiptItem[];
  suggested_category_id: string | null;
  suggested_category_name: string | null;
}

export interface Receipt {
  id: string;
  transaction_id: string | null;
  original_filename: string | null;
  content_type: string;
  file_size_bytes: number;
  status: ReceiptStatus;

  extraction: ReceiptExtraction | null;

  confirmed_merchant: string | null;
  confirmed_date: string | null;
  confirmed_total_minor: number | null;
  confirmed_tax_minor: number | null;
  confirmed_items: ReceiptItem[];
  category_id: string | null;
  category_name: string | null;
  category_icon: string | null;
  category_color: string | null;
  confirmed_at: string | null;

  created_at: string;
  updated_at: string;
}

export interface ReceiptConfirmInput {
  merchant?: string | null;
  date?: string | null;
  total_minor?: number | null;
  tax_minor?: number | null;
  items?: ReceiptItem[];
  category_id?: string | null;
}

export async function listReceipts(accessToken: string): Promise<Receipt[]> {
  return apiRequest<Receipt[]>("/api/v1/receipts", { accessToken });
}

export async function getReceipt(accessToken: string, receiptId: string): Promise<Receipt> {
  return apiRequest<Receipt>(`/api/v1/receipts/${receiptId}`, { accessToken });
}

export async function uploadReceipt(accessToken: string, file: File): Promise<Receipt> {
  const formData = new FormData();
  formData.append("file", file);
  return apiUpload<Receipt>("/api/v1/receipts/upload", formData, { accessToken });
}

export async function confirmReceipt(
  accessToken: string,
  receiptId: string,
  input: ReceiptConfirmInput
): Promise<Receipt> {
  return apiRequest<Receipt>(`/api/v1/receipts/${receiptId}/confirm`, {
    method: "PUT",
    accessToken,
    body: input,
  });
}

export async function createTransactionFromReceipt(
  accessToken: string,
  receiptId: string,
  accountId: string
): Promise<Transaction> {
  return apiRequest<Transaction>(`/api/v1/receipts/${receiptId}/transaction`, {
    method: "POST",
    accessToken,
    body: { account_id: accountId },
  });
}

export async function deleteReceipt(accessToken: string, receiptId: string): Promise<void> {
  await apiRequest(`/api/v1/receipts/${receiptId}`, { method: "DELETE", accessToken });
}

/** Fetches a receipt's stored file as an object URL for inline preview. The
 * caller must revoke it (URL.revokeObjectURL) once it's no longer shown. */
export async function getReceiptFileUrl(accessToken: string, receiptId: string): Promise<string> {
  const blob = await apiFetchBlob(`/api/v1/receipts/${receiptId}/file`, accessToken);
  return URL.createObjectURL(blob);
}
