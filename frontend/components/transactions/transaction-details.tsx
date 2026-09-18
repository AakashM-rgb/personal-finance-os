"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import type { Transaction } from "@/lib/transactions";

interface TransactionDetailsProps {
  transaction: Transaction;
  account: Account | undefined;
  transferAccount: Account | undefined;
  category: Category | undefined;
  onEdit: () => void;
  onDuplicate: () => Promise<void>;
  onDelete: () => Promise<void>;
}

const TYPE_LABEL: Record<Transaction["type"], string> = {
  income: "Income",
  expense: "Expense",
  transfer: "Transfer",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
      <span className="text-sm text-zinc-900 dark:text-zinc-50">{children}</span>
    </div>
  );
}

export function TransactionDetails({
  transaction,
  account,
  transferAccount,
  category,
  onEdit,
  onDuplicate,
  onDelete,
}: TransactionDetailsProps) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isBusy, setIsBusy] = useState(false);

  async function handleDuplicateClick() {
    setIsBusy(true);
    try {
      await onDuplicate();
    } finally {
      setIsBusy(false);
    }
  }

  async function handleConfirmDelete() {
    setIsBusy(true);
    try {
      await onDelete();
    } finally {
      setIsBusy(false);
      setIsConfirmingDelete(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          {TYPE_LABEL[transaction.type]}
        </p>
        <p className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          {formatMoney(transaction.amount_minor, transaction.currency)}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Date">{formatDateTime(transaction.occurred_at)}</Field>
        <Field label={transaction.type === "transfer" ? "From account" : "Account"}>
          {account?.name ?? "—"}
        </Field>

        {transaction.type === "transfer" ? (
          <Field label="To account">{transferAccount?.name ?? "—"}</Field>
        ) : (
          <Field label="Category">
            {category ? `${category.icon} ${category.name}` : "No category"}
          </Field>
        )}

        <Field label="Description">{transaction.description || "—"}</Field>

        {transaction.merchant && <Field label="Merchant">{transaction.merchant}</Field>}
        {transaction.payment_method && (
          <Field label="Payment method">{transaction.payment_method}</Field>
        )}

        <Field label="Tags">
          {transaction.tags.length > 0 ? transaction.tags.map((t) => `#${t}`).join(" ") : "—"}
        </Field>

        <Field label="Recurring">{transaction.is_recurring ? "Yes" : "No"}</Field>

        <Field label="Source">
          {transaction.linked_account_id ? "🔄 Automatically synced" : "Manual"}
        </Field>

        {transaction.needs_review && (
          <Field label="Review">Needs review - category not auto-assigned</Field>
        )}

        {transaction.notes && (
          <div className="col-span-2 flex flex-col gap-0.5">
            <span className="text-xs text-zinc-500 dark:text-zinc-400">Notes</span>
            <span className="text-sm text-zinc-900 dark:text-zinc-50">{transaction.notes}</span>
          </div>
        )}

        <Field label="Created">{formatDateTime(transaction.created_at)}</Field>
        <Field label="Last updated">{formatDateTime(transaction.updated_at)}</Field>
      </div>

      <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4 dark:border-zinc-800">
        {isConfirmingDelete ? (
          <>
            <Button variant="secondary" onClick={() => setIsConfirmingDelete(false)}>
              Cancel
            </Button>
            <Button
              className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
              isLoading={isBusy}
              onClick={() => void handleConfirmDelete()}
            >
              Confirm delete
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={onEdit}>
              Edit
            </Button>
            <Button variant="ghost" isLoading={isBusy} onClick={() => void handleDuplicateClick()}>
              Duplicate
            </Button>
            <Button variant="ghost" onClick={() => setIsConfirmingDelete(true)}>
              Delete
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
