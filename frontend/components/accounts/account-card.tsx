"use client";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Card } from "@/components/ui/card";
import {
  ACCOUNT_TYPE_LABELS,
  describeCardBalance,
  utilizationBarPercent,
  type Account,
} from "@/lib/accounts";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import { useConfirmableAction } from "@/lib/use-confirmable-action";

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
  const confirmAction = useConfirmableAction(
    onDelete,
    "Couldn't delete this account. Please try again."
  );

  const creditCard = account.credit_card;
  const utilization = Math.max(creditCard?.utilization_percent ?? 0, 0);
  const barPercent = utilizationBarPercent(utilization);
  const utilizationLevel =
    utilization >= 90 ? "high" : utilization >= 70 ? "medium" : "low";
  const cardBalance = creditCard ? describeCardBalance(account.balance_minor) : null;

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
        {formatMoney(cardBalance ? cardBalance.amountMinor : account.balance_minor, account.currency)}
        <span
          className={cn(
            "ml-2 text-xs font-normal",
            cardBalance?.label === "credit balance"
              ? "text-emerald-700 dark:text-emerald-400"
              : "text-zinc-500 dark:text-zinc-400"
          )}
        >
          {cardBalance ? cardBalance.label : "balance"}
        </span>
      </p>

      {creditCard && (
        <div className="flex flex-col gap-1.5">
          <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
            <div
              role="progressbar"
              aria-label="Credit utilization"
              aria-valuenow={barPercent}
              aria-valuemin={0}
              aria-valuemax={100}
              className={cn(
                "h-full rounded-full",
                utilizationLevel === "high" && "bg-red-500",
                utilizationLevel === "medium" && "bg-amber-500",
                utilizationLevel === "low" && "bg-emerald-500"
              )}
              style={{ width: `${barPercent}%` }}
            />
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {utilization.toFixed(2)}% utilized · {formatMoney(creditCard.available_credit_minor, account.currency)}{" "}
            available of {formatMoney(creditCard.credit_limit_minor, account.currency)}
          </p>
          {/* Over limit is its own, more specific statement than "high
              utilization": available credit is 0 and the overshoot is a real
              amount the user needs to see. */}
          {creditCard.over_limit_minor > 0 ? (
            <p className="text-xs font-medium text-red-600 dark:text-red-400">
              {formatMoney(creditCard.over_limit_minor, account.currency)} over the credit limit -
              pay this down to restore available credit.
            </p>
          ) : (
            utilizationLevel === "high" && (
              <p className="text-xs font-medium text-red-600 dark:text-red-400">
                High utilization - consider paying this down.
              </p>
            )
          )}
        </div>
      )}

      <div className="mt-1 flex justify-end gap-2">
        {confirmAction.isConfirming ? (
          <>
            <Button variant="secondary" onClick={confirmAction.cancel}>
              Cancel
            </Button>
            <Button
              variant="primary"
              className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
              isLoading={confirmAction.isPending}
              onClick={() => void confirmAction.confirm()}
            >
              Confirm delete
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={onEdit}>
              Edit
            </Button>
            <Button variant="ghost" onClick={confirmAction.start}>
              Delete
            </Button>
          </>
        )}
      </div>
      <FormError message={confirmAction.error} />
    </Card>
  );
}
