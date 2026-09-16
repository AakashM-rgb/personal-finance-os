"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { ReceiptReviewForm } from "@/components/receipts/receipt-review-form";
import type { Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import {
  confirmReceipt,
  createTransactionFromReceipt,
  deleteReceipt,
  getReceipt,
  getReceiptFileUrl,
  type Receipt,
  type ReceiptConfirmInput,
} from "@/lib/receipts";

interface ReceiptDetailModalProps {
  receipt: Receipt;
  accounts: Account[];
  categories: Category[];
  accessToken: string;
  onClose: () => void;
  onChanged: (receipt: Receipt) => void;
  onDeleted: (receiptId: string) => void;
}

export function ReceiptDetailModal({
  receipt,
  accounts,
  categories,
  accessToken,
  onClose,
  onChanged,
  onDeleted,
}: ReceiptDetailModalProps) {
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? "");
  const [transactionError, setTransactionError] = useState<string | null>(null);
  const [isCreatingTransaction, setIsCreatingTransaction] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    let objectUrl: string | null = null;

    void getReceiptFileUrl(accessToken, receipt.id).then((url) => {
      if (!isMounted) {
        URL.revokeObjectURL(url);
        return;
      }
      objectUrl = url;
      setFileUrl(url);
    });

    return () => {
      isMounted = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [accessToken, receipt.id]);

  async function handleConfirm(input: ReceiptConfirmInput) {
    const updated = await confirmReceipt(accessToken, receipt.id, input);
    onChanged(updated);
  }

  async function handleCreateTransaction() {
    if (!accountId) {
      setTransactionError("Choose an account first.");
      return;
    }
    setTransactionError(null);
    setIsCreatingTransaction(true);
    try {
      await createTransactionFromReceipt(accessToken, receipt.id, accountId);
      onChanged(await getReceipt(accessToken, receipt.id));
    } catch (err) {
      setTransactionError(err instanceof ApiError ? err.message : "Failed to create a transaction.");
    } finally {
      setIsCreatingTransaction(false);
    }
  }

  async function handleDelete() {
    setDeleteError(null);
    setIsDeleting(true);
    try {
      await deleteReceipt(accessToken, receipt.id);
      onDeleted(receipt.id);
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Failed to delete the receipt.");
      setIsDeleting(false);
    }
  }

  const isImage = receipt.content_type.startsWith("image/");

  return (
    <Modal title="Receipt" onClose={onClose}>
      <div className="flex flex-col gap-4">
        {fileUrl && isImage && (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated blob URL, not an optimizable remote asset
          <img
            src={fileUrl}
            alt="Receipt scan"
            className="max-h-48 w-full rounded-md border border-zinc-200 object-contain dark:border-zinc-800"
          />
        )}
        {fileUrl && !isImage && (
          <a
            href={fileUrl}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-medium text-zinc-700 underline hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-100"
          >
            Open {receipt.original_filename ?? "receipt file"} (PDF)
          </a>
        )}

        <ReceiptReviewForm receipt={receipt} categories={categories} onSubmit={handleConfirm} />

        {receipt.status === "confirmed" && !receipt.transaction_id && (
          <div className="flex flex-col gap-2 border-t border-zinc-200 pt-4 dark:border-zinc-800">
            <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Create a transaction</p>
            <div className="flex gap-2">
              <Select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </Select>
              <Button
                type="button"
                variant="secondary"
                onClick={handleCreateTransaction}
                isLoading={isCreatingTransaction}
              >
                {receipt.confirmed_total_minor !== null
                  ? `Add ${formatMoney(receipt.confirmed_total_minor)}`
                  : "Add expense"}
              </Button>
            </div>
            <FormError message={transactionError} />
          </div>
        )}

        {receipt.transaction_id && (
          <p className="text-sm text-emerald-700 dark:text-emerald-400">
            A transaction has already been created from this receipt.
          </p>
        )}

        <div className="flex items-center justify-between border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <Button type="button" variant="ghost" onClick={handleDelete} isLoading={isDeleting}>
            Delete receipt
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
        <FormError message={deleteError} />
      </div>
    </Modal>
  );
}
