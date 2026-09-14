"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ACCOUNT_TYPE_LABELS, type Account } from "@/lib/accounts";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const ACCOUNT_TYPE_ICONS: Record<Account["type"], string> = {
  bank_account: "🏦",
  cash: "💵",
  credit_card: "💳",
  upi: "📱",
  savings_account: "🏛️",
  wallet: "👛",
};

interface AccountCardProps {
  account: Account;
  onEdit: () => void;
  onDelete: () => Promise<void>;
}

export function AccountCard({ account, onEdit, onDelete }: AccountCardProps) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const creditCard = account.credit_card;
  const utilization = creditCard?.utilization_percent ?? 0;
  const utilizationLevel =
    utilization >= 90 ? "high" : utilization >= 70 ? "medium" : "low";

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
        <div className="flex items-center gap-3">
          <span className="text-2xl" aria-hidden="true">
            {ACCOUNT_TYPE_ICONS[account.type]}
          </span>
          <div>
            <p className="font-medium text-zinc-900 dark:text-zinc-50">{account.name}</p>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {ACCOUNT_TYPE_LABELS[account.type]}
              {account.institution_name ? ` · ${account.institution_name}` : ""}
            </p>
          </div>
        </div>
      </div>

      <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
        {formatMoney(account.balance_minor, account.currency)}
        <span className="ml-2 text-xs font-normal text-zinc-500 dark:text-zinc-400">
          {creditCard ? "owed" : "balance"}
        </span>
      </p>

      {creditCard && (
        <div className="flex flex-col gap-1.5">
          <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
            <div
              role="progressbar"
              aria-valuenow={Math.min(utilization, 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              className={cn(
                "h-full rounded-full",
                utilizationLevel === "high" && "bg-red-500",
                utilizationLevel === "medium" && "bg-amber-500",
                utilizationLevel === "low" && "bg-emerald-500"
              )}
              style={{ width: `${Math.min(utilization, 100)}%` }}
            />
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {utilization.toFixed(2)}% utilized · {formatMoney(creditCard.available_credit_minor, account.currency)}{" "}
            available of {formatMoney(creditCard.credit_limit_minor, account.currency)}
          </p>
          {utilizationLevel === "high" && (
            <p className="text-xs font-medium text-red-600 dark:text-red-400">
              High utilization - consider paying this down.
            </p>
          )}
        </div>
      )}

      <div className="mt-1 flex justify-end gap-2">
        {isConfirmingDelete ? (
          <>
            <Button variant="secondary" onClick={() => setIsConfirmingDelete(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
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
