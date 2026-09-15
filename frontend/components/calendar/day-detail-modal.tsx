"use client";

import { Modal } from "@/components/ui/modal";
import type { Account } from "@/lib/accounts";
import type { CalendarDay } from "@/lib/calendar";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

interface DayDetailModalProps {
  day: CalendarDay;
  currency: string;
  accounts: Account[];
  categories: Category[];
  onClose: () => void;
}

function formatDateLabel(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function DayDetailModal({ day, currency, accounts, categories, onClose }: DayDetailModalProps) {
  const accountsById = new Map(accounts.map((a) => [a.id, a]));
  const categoriesById = new Map(categories.map((c) => [c.id, c]));

  return (
    <Modal title={formatDateLabel(day.date)} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <div className="flex justify-between text-sm">
          <span className="text-emerald-600 dark:text-emerald-400">
            Income: {formatMoney(day.income_minor, currency)}
          </span>
          <span className="text-red-600 dark:text-red-400">
            Expense: {formatMoney(day.expense_minor, currency)}
          </span>
        </div>

        {day.bills.length > 0 && (
          <div className="rounded-md border border-dashed border-amber-300 p-3 dark:border-amber-800">
            <p className="mb-2 text-xs font-medium text-amber-700 dark:text-amber-400">
              Scheduled (not yet paid)
            </p>
            <ul className="flex flex-col gap-1.5">
              {day.bills.map((bill) => (
                <li
                  key={bill.recurring_transaction_id}
                  className="flex justify-between text-sm text-zinc-700 dark:text-zinc-300"
                >
                  <span>
                    {bill.name}
                    {bill.is_subscription && (
                      <span className="ml-1.5 rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-400">
                        Subscription
                      </span>
                    )}
                  </span>
                  <span>{formatMoney(bill.amount_minor, bill.currency)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <p className="mb-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
            Transactions
          </p>
          {day.transactions.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No transactions recorded on this day.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {day.transactions.map((txn) => {
                const account = accountsById.get(txn.account_id);
                const category = txn.category_id ? categoriesById.get(txn.category_id) : undefined;
                const time = new Date(txn.occurred_at).toLocaleTimeString(undefined, {
                  hour: "numeric",
                  minute: "2-digit",
                });
                return (
                  <li
                    key={txn.id}
                    className="flex items-center justify-between rounded-md border border-zinc-200 p-2.5 text-sm dark:border-zinc-800"
                  >
                    <div className="flex flex-col">
                      <span className="text-zinc-900 dark:text-zinc-50">
                        {txn.description || category?.name || "Transaction"}
                      </span>
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">
                        {time} &middot; {account?.name ?? "Unknown account"}
                        {category ? ` · ${category.name}` : ""}
                        {txn.type === "transfer" ? " · Transfer" : ""}
                      </span>
                    </div>
                    <span
                      className={cn(
                        "font-medium",
                        txn.type === "income"
                          ? "text-emerald-600 dark:text-emerald-400"
                          : txn.type === "transfer"
                            ? "text-zinc-500 dark:text-zinc-400"
                            : "text-red-600 dark:text-red-400"
                      )}
                    >
                      {txn.type === "income" ? "+" : txn.type === "expense" ? "-" : ""}
                      {formatMoney(txn.amount_minor, txn.currency)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
}
