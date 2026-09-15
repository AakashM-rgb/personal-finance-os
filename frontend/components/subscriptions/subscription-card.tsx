"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FREQUENCY_LABELS } from "@/lib/recurring-transactions";
import { formatMoney } from "@/lib/money";
import type { Subscription } from "@/lib/subscriptions";
import { cn } from "@/lib/utils";

function formatDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

interface SubscriptionCardProps {
  subscription: Subscription;
  onEdit: () => void;
  onDeactivate: () => Promise<void>;
}

export function SubscriptionCard({ subscription, onEdit, onDeactivate }: SubscriptionCardProps) {
  const [isConfirmingDeactivate, setIsConfirmingDeactivate] = useState(false);
  const [isDeactivating, setIsDeactivating] = useState(false);

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
    <Card className={cn("flex flex-col gap-3", !subscription.is_active && "opacity-60")}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          {subscription.category_icon && (
            <span className="text-xl" aria-hidden="true">
              {subscription.category_icon}
            </span>
          )}
          <span className="font-medium text-zinc-900 dark:text-zinc-50">{subscription.name}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {subscription.is_possibly_unused === true && (
            <span
              title={subscription.unused_reason}
              className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-400"
            >
              Possibly unused
            </span>
          )}
          <span
            className={cn(
              "rounded-full px-2.5 py-0.5 text-xs font-medium",
              subscription.is_active
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
            )}
          >
            {subscription.is_active ? "Active" : "Inactive"}
          </span>
        </div>
      </div>

      <div>
        <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          {formatMoney(subscription.amount_minor, subscription.currency)}
          <span className="text-sm font-normal text-zinc-500 dark:text-zinc-400">
            {" "}
            / {FREQUENCY_LABELS[subscription.frequency].toLowerCase()}
          </span>
        </p>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          {formatMoney(subscription.monthly_cost_minor, subscription.currency)}/month ·{" "}
          {formatMoney(subscription.yearly_cost_minor, subscription.currency)}/year
        </p>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
        <span>{subscription.account_name}</span>
        {subscription.category_name && <span>{subscription.category_name}</span>}
      </div>

      <p
        className="text-xs text-zinc-500 dark:text-zinc-400"
        title={subscription.is_possibly_unused === null ? subscription.unused_reason : undefined}
      >
        Next renewal:{" "}
        <span className="font-medium text-zinc-700 dark:text-zinc-300">
          {formatDate(subscription.next_renewal_date)}
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
            {subscription.is_active && (
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
