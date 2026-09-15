"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { getGoalStatus, type GoalStatus, type SavingsGoal } from "@/lib/goals";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<GoalStatus, { bar: string; badge: string; label: string }> = {
  completed: {
    bar: "bg-emerald-600",
    badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
    label: "Completed",
  },
  on_track: {
    bar: "bg-blue-600",
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
    label: "On track",
  },
  due_today: {
    bar: "bg-amber-500",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
    label: "Due today",
  },
  overdue: {
    bar: "bg-red-600",
    badge: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
    label: "Overdue",
  },
};

function formatTargetDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

interface GoalCardProps {
  goal: SavingsGoal;
  onEdit: () => void;
  onDelete: () => Promise<void>;
}

export function GoalCard({ goal, onEdit, onDelete }: GoalCardProps) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const status = getGoalStatus(goal);
  const style = STATUS_STYLES[status];
  const currency = goal.currency;

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
        <span className="font-medium text-zinc-900 dark:text-zinc-50">{goal.name}</span>
        <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", style.badge)}>
          {style.label}
        </span>
      </div>

      <div>
        <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          {formatMoney(goal.current_amount_minor, currency)}
          <span className="text-sm font-normal text-zinc-500 dark:text-zinc-400">
            {" "}
            / {formatMoney(goal.target_amount_minor, currency)}
          </span>
        </p>
        <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
          <div
            role="progressbar"
            aria-valuenow={Math.min(goal.progress_percent, 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            className={cn("h-full rounded-full", style.bar)}
            style={{ width: `${Math.min(goal.progress_percent, 100)}%` }}
          />
        </div>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          {goal.progress_percent.toFixed(1)}% saved ·{" "}
          {goal.remaining_minor > 0
            ? `${formatMoney(goal.remaining_minor, currency)} to go`
            : "Goal reached"}
        </p>
      </div>

      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Target date: <span className="font-medium">{formatTargetDate(goal.target_date)}</span>
      </p>

      {!goal.is_completed && (
        <p
          className={cn(
            "text-xs font-medium",
            status === "overdue"
              ? "text-red-600 dark:text-red-400"
              : "text-zinc-700 dark:text-zinc-300"
          )}
        >
          {status === "overdue"
            ? "Target date has passed - update the date or your saved amount to see a savings pace."
            : status === "due_today"
              ? "Your target date is today - update the date or your saved amount to see a savings pace."
              : `Save ${formatMoney(
                goal.required_monthly_savings_minor ?? 0,
                currency
              )}/month (${formatMoney(
                goal.required_weekly_savings_minor ?? 0,
                currency
              )}/week) to reach your target by ${formatTargetDate(goal.target_date)}.`}
        </p>
      )}

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
