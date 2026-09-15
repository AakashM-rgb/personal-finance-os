import Link from "next/link";

import { Card } from "@/components/ui/card";
import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import type { Transaction } from "@/lib/transactions";
import { cn } from "@/lib/utils";

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

interface RecentTransactionsListProps {
  transactions: Transaction[];
  accountsById: Map<string, Account>;
  categoriesById: Map<string, Category>;
}

export function RecentTransactionsList({
  transactions,
  accountsById,
  categoriesById,
}: RecentTransactionsListProps) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Recent transactions
        </h2>
        <Link
          href="/transactions"
          className="text-xs font-medium text-zinc-500 underline dark:text-zinc-400"
        >
          View all
        </Link>
      </div>

      {transactions.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
          You haven&apos;t recorded any transactions yet.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col">
          {transactions.map((txn) => {
            const category = txn.category_id ? categoriesById.get(txn.category_id) : undefined;
            const account = accountsById.get(txn.account_id);
            return (
              <li
                key={txn.id}
                className="flex items-center justify-between gap-3 border-b border-zinc-100 py-2.5 last:border-0 dark:border-zinc-800"
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm"
                    style={{ backgroundColor: category ? `${category.color}22` : "#e4e4e722" }}
                    aria-hidden="true"
                  >
                    {txn.type === "transfer" ? "🔁" : category?.icon ?? "🏷️"}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
                      {txn.description || txn.merchant || category?.name || "Transaction"}
                    </p>
                    <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                      {account?.name ?? ""}
                    </p>
                  </div>
                </div>
                <span className={cn("shrink-0 text-sm font-medium", TYPE_COLOR[txn.type])}>
                  {TYPE_SIGN[txn.type]}
                  {formatMoney(txn.amount_minor, txn.currency)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
