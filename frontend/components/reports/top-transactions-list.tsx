import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import type { Transaction } from "@/lib/transactions";

interface TopTransactionsListProps {
  transactions: Transaction[];
  accounts: Account[];
  categories: Category[];
  emptyMessage: string;
}

function formatDateLabel(isoDateTime: string): string {
  return new Date(isoDateTime).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function TopTransactionsList({
  transactions,
  accounts,
  categories,
  emptyMessage,
}: TopTransactionsListProps) {
  if (transactions.length === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">{emptyMessage}</p>;
  }

  const accountsById = new Map(accounts.map((a) => [a.id, a]));
  const categoriesById = new Map(categories.map((c) => [c.id, c]));

  return (
    <ul className="flex flex-col gap-2">
      {transactions.map((txn) => {
        const account = accountsById.get(txn.account_id);
        const category = txn.category_id ? categoriesById.get(txn.category_id) : undefined;
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
                {formatDateLabel(txn.occurred_at)} &middot; {account?.name ?? "Unknown account"}
                {category ? ` · ${category.name}` : ""}
              </span>
            </div>
            <span className="font-medium text-zinc-900 dark:text-zinc-50">
              {formatMoney(txn.amount_minor, txn.currency)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
