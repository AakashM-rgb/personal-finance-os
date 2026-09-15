import { Card } from "@/components/ui/card";
import type { UpcomingPayment } from "@/lib/dashboard";
import { formatMoney } from "@/lib/money";

function formatDueDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function UpcomingPaymentsList({
  payments,
  currency,
}: {
  payments: UpcomingPayment[];
  currency: string;
}) {
  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Upcoming payments</h2>

      {payments.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
          No upcoming credit card payments due.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2.5">
          {payments.map((payment, index) => (
            <li key={`${payment.account_id}-${index}`} className="flex items-center justify-between text-sm">
              <div>
                <p className="font-medium text-zinc-900 dark:text-zinc-50">{payment.description}</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Due {formatDueDate(payment.due_date)}
                </p>
              </div>
              <span className="font-medium text-zinc-900 dark:text-zinc-50">
                {formatMoney(payment.amount_minor, currency)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
