import { Card } from "@/components/ui/card";
import type { RecurringExpenseBreakdown } from "@/lib/analytics";
import { FREQUENCY_LABELS } from "@/lib/recurring-transactions";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

interface RecurringExpenseBreakdownListProps {
  data: RecurringExpenseBreakdown;
  currency: string;
}

export function RecurringExpenseBreakdownList({
  data,
  currency,
}: RecurringExpenseBreakdownListProps) {
  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
        Recurring expense breakdown
      </h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        How much of my spending is committed to recurring expenses?
      </p>

      {data.recurring_share_of_expense_percent !== null && (
        <p className="mt-3 text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          {data.recurring_share_of_expense_percent.toFixed(1)}%
          <span className="ml-2 text-sm font-normal text-zinc-500 dark:text-zinc-400">
            of real spending in this range was recurring
          </span>
        </p>
      )}

      {data.items.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          No recurring expenses set up yet.
        </p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
            <span>
              Current commitment:{" "}
              <span className="font-medium text-zinc-700 dark:text-zinc-300">
                {formatMoney(data.total_scheduled_monthly_minor, currency)}/month
              </span>
            </span>
            <span>
              Actually paid in range:{" "}
              <span className="font-medium text-zinc-700 dark:text-zinc-300">
                {formatMoney(data.total_actual_paid_minor, currency)}
              </span>
            </span>
          </div>

          <ul className="mt-4 flex flex-col gap-3">
            {data.items.map((item) => (
              <li
                key={item.recurring_transaction_id}
                className={cn("flex items-center justify-between text-sm", !item.is_active && "opacity-60")}
              >
                <div className="flex items-center gap-2">
                  <span className="text-zinc-700 dark:text-zinc-300">{item.name}</span>
                  {item.is_subscription && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-400">
                      Subscription
                    </span>
                  )}
                  {!item.is_active && (
                    <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                      Inactive
                    </span>
                  )}
                </div>
                <div className="text-right text-xs text-zinc-500 dark:text-zinc-400">
                  <p>
                    {formatMoney(item.scheduled_monthly_cost_minor, item.currency)}/mo &middot;{" "}
                    {FREQUENCY_LABELS[item.frequency]}
                  </p>
                  <p>Paid this range: {formatMoney(item.actual_paid_minor, item.currency)}</p>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
