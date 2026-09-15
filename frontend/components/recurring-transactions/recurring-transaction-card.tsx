"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FREQUENCY_LABELS, isOverdue, type RecurringTransaction } from "@/lib/recurring-transactions";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

function formatDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

interface RecurringTransactionCardProps {
  recurring: RecurringTransaction;
  onEdit: () => void;
  onDeactivate: () => Promise<void>;
}

export function RecurringTransactionCard({
  recurring,
  onEdit,
  onDeactivate,
}: RecurringTransactionCardProps) {
  const [isConfirmingDeactivate, setIsConfirmingDeactivate] = useState(false);
  const [isDeactivating, setIsDeactivating] = useState(false);
  const overdue = isOverdue(recurring, new Date().toISOString().slice(0, 10));

  async function handleConfirmDeactivate() {
    setIsDeactivating(true);
    try {
      await onDeactivate();
    } finally {
      setIsDeactivating(false);
      setIsConfirmingDeactivate(false);
    }
  }

  return (
    <Card className={cn("flex flex-col gap-3", !recurring.is_active && "opacity-60")}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          {recurring.category_icon && (
            <span className="text-xl" aria-hidden="true">
              {recurring.category_icon}
            </span>
          )}
          <span className="font-medium text-zinc-900 dark:text-zinc-50">{recurring.name}</span>
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium",
            !recurring.is_active
              ? "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
              : overdue
                ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400"
                : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
          )}
        >
          {!recurring.is_active ? "Inactive" : overdue ? "Overdue" : "Active"}
        </span>
      </div>

      <p
        className={cn(
          "text-lg font-semibold",
          recurring.type === "income"
            ? "text-emerald-600 dark:text-emerald-400"
            : "text-zinc-900 dark:text-zinc-50"
        )}
      >
        {recurring.type === "income" ? "+" : "-"}
        {formatMoney(recurring.amount_minor, recurring.currency)}
      </p>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
        <span>{recurring.account_name}</span>
        {recurring.category_name && <span>{recurring.category_name}</span>}
        <span>{FREQUENCY_LABELS[recurring.frequency]}</span>
      </div>

      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Next occurrence:{" "}
        <span className="font-medium text-zinc-700 dark:text-zinc-300">
          {formatDate(recurring.next_occurrence_date)}
        </span>
      </p>

      <div className="mt-1 flex justify-end gap-2">
        {isConfirmingDeactivate ? (
          <>
            <Button variant="secondary" onClick={() => setIsConfirmingDeactivate(false)}>
              Cancel
            </Button>
            <Button
              className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
              isLoading={isDeactivating}
              onClick={() => void handleConfirmDeactivate()}
            >
              Confirm deactivate
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={onEdit}>
              Edit
            </Button>
            {recurring.is_active && (
              <Button variant="ghost" onClick={() => setIsConfirmingDeactivate(true)}>
                Deactivate
              </Button>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
