"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import type { Transaction } from "@/lib/transactions";

interface TransactionRowProps {
  transaction: Transaction;
  account: Account | undefined;
  transferAccount: Account | undefined;
  category: Category | undefined;
  onView: () => void;
  onEdit: () => void;
  onDuplicate: () => Promise<void>;
  onDelete: () => Promise<void>;
}

const TYPE_COLOR: Record<Transaction["type"], string> = {
  income: "text-emerald-600 dark:text-emerald-400",
  expense: "text-red-600 dark:text-red-400",
  transfer: "text-zinc-600 dark:text-zinc-400",
};

const TYPE_SIGN: Record<Transaction["type"], string> = {
  income: "+",
  expense: "-",
  transfer: "",
};

export function TransactionRow({
  transaction,
  account,
  transferAccount,
  category,
  onView,
  onEdit,
  onDuplicate,
  onDelete,
}: TransactionRowProps) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isBusy, setIsBusy] = useState(false);

  async function handleConfirmDelete() {
    setIsBusy(true);
    try {
      await onDelete();
    } finally {
      setIsBusy(false);
      setIsConfirmingDelete(false);
    }
  }

  const date = new Date(transaction.occurred_at);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-100 py-3 last:border-0 dark:border-zinc-800">
      <button
        type="button"
        onClick={onView}
        className="flex min-w-0 flex-1 items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:focus-visible:ring-zinc-100"
      >
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-base"
          style={{ backgroundColor: category ? `${category.color}22` : "#e4e4e722" }}
          aria-hidden="true"
        >
          {transaction.type === "transfer" ? "🔁" : category?.icon ?? "🏷️"}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
            {transaction.description || transaction.merchant || category?.name || "Transaction"}
            {transaction.is_recurring && (
              <span className="ml-2 rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                Recurring
              </span>
            )}
          </p>
          <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
            {date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
            {" · "}
            {transaction.type === "transfer"
              ? `${account?.name ?? "?"} → ${transferAccount?.name ?? "?"}`
              : account?.name ?? "?"}
            {category && transaction.type !== "transfer" ? ` · ${category.name}` : ""}
            {transaction.tags.length > 0 ? ` · #${transaction.tags.join(" #")}` : ""}
          </p>
        </div>
      </button>

      <p className={`text-sm font-semibold ${TYPE_COLOR[transaction.type]}`}>
        {TYPE_SIGN[transaction.type]}
        {formatMoney(transaction.amount_minor, transaction.currency)}
      </p>

      <div className="flex gap-1">
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
              Confirm
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={onEdit}>
              Edit
            </Button>
            <Button variant="ghost" onClick={() => void onDuplicate()}>
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
