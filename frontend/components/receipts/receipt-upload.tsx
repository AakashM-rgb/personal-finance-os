"use client";

import { useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { FormError } from "@/components/ui/form-error";
import { ApiError } from "@/lib/api-client";
import {
  RECEIPT_ACCEPTED_CONTENT_TYPES,
  RECEIPT_MAX_FILE_SIZE_BYTES,
  uploadReceipt,
  validateReceiptFile,
  type Receipt,
} from "@/lib/receipts";

interface ReceiptUploadProps {
  accessToken: string;
  onUploaded: (receipt: Receipt) => void;
}

export function ReceiptUpload({ accessToken, onUploaded }: ReceiptUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    const validationError = validateReceiptFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setIsUploading(true);
    try {
      const receipt = await uploadReceipt(accessToken, file);
      onUploaded(receipt);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to upload the receipt.");
    } finally {
      setIsUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void handleFile(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
          isDragging
            ? "border-zinc-900 bg-zinc-50 dark:border-zinc-100 dark:bg-zinc-900"
            : "border-zinc-300 dark:border-zinc-700"
        }`}
      >
        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
          {isUploading ? "Uploading…" : "Drop a receipt here, or click to choose a file"}
        </p>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          JPG, PNG, or PDF — up to {RECEIPT_MAX_FILE_SIZE_BYTES / (1024 * 1024)}MB
        </p>
        {/* The real, natively keyboard-accessible control - the wrapping div is
            just a larger mouse/drag target for the same input, not a second
            interactive element (no role="button"/tabIndex there). */}
        <input
          ref={inputRef}
          type="file"
          aria-label="Upload a receipt (JPG, PNG, or PDF)"
          accept={RECEIPT_ACCEPTED_CONTENT_TYPES.join(",")}
          className="sr-only"
          onChange={handleInputChange}
          disabled={isUploading}
        />
      </div>
      <FormError message={error} />
    </div>
  );
}
