"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { Budget, BudgetStatus } from "@/lib/budgets";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<BudgetStatus, { bar: string; badge: string; label: string }> = {
  healthy: {
    bar: "bg-emerald-600",
    badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
    label: "Healthy",
  },
  warning: {
    bar: "bg-amber-500",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
    label: "Warning",
  },
  near_limit: {
    bar: "bg-orange-500",
    badge: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400",
    label: "Near limit",
  },
  exceeded: {
    bar: "bg-red-600",
    badge: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
    label: "Exceeded",
  },
};

interface BudgetCardProps {
  budget: Budget;
  currency: string;
  onEdit: () => void;
  onDelete: () => Promise<void>;
}

export function BudgetCard({ budget, currency, onEdit, onDelete }: BudgetCardProps) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const style = STATUS_STYLES[budget.status];

  async function handleConfirmDelete() {
    setIsDeleting(true);
    try {
      await onDelete();
    } finally {
      setIsDeleting(false);
      setIsConfirmingDelete(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-xl" aria-hidden="true">
            {budget.category_icon}
          </span>
          <span className="font-medium text-zinc-900 dark:text-zinc-50">
            {budget.category_name}
          </span>
        </div>
        <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", style.badge)}>
          {style.label}
        </span>
      </div>

      <div>
        <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          {formatMoney(budget.spent_minor, currency)}
          <span className="text-sm font-normal text-zinc-500 dark:text-zinc-400">
            {" "}
            / {formatMoney(budget.amount_minor, currency)}
          </span>
        </p>
        <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
          <div
            role="progressbar"
            aria-valuenow={Math.min(budget.percent_used, 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            className={cn("h-full rounded-full", style.bar)}
            style={{ width: `${Math.min(budget.percent_used, 100)}%` }}
          />
        </div>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          {budget.percent_used.toFixed(1)}% used ·{" "}
          {budget.remaining_minor >= 0
            ? `${formatMoney(budget.remaining_minor, currency)} left`
            : `${formatMoney(-budget.remaining_minor, currency)} over`}
        </p>
      </div>

      {budget.warning_message && (
        <p
          className={cn(
            "text-xs font-medium",
            budget.status === "exceeded"
              ? "text-red-600 dark:text-red-400"
              : "text-amber-600 dark:text-amber-400"
          )}
        >
          {budget.warning_message}
        </p>
      )}

      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        At this rate, you&apos;ll spend approximately{" "}
        <span className="font-medium text-zinc-700 dark:text-zinc-300">
          {formatMoney(budget.projected_month_minor, currency)}
        </span>{" "}
        on {budget.category_name.toLowerCase()} this month.
      </p>

      <div className="mt-1 flex justify-end gap-2">
        {isConfirmingDelete ? (
          <>
            <Button variant="secondary" onClick={() => setIsConfirmingDelete(false)}>
              Cancel
            </Button>
            <Button
              className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
              isLoading={isDeleting}
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
            <Button variant="ghost" onClick={() => setIsConfirmingDelete(true)}>
              Delete
            </Button>
          </>
        )}
      </div>
    </Card>
  );
}
