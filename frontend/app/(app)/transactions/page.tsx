"use client";

import { useEffect, useState } from "react";

import { QuickAddBar } from "@/components/transactions/quick-add-bar";
import { TransactionDetails } from "@/components/transactions/transaction-details";
import { TransactionFiltersBar } from "@/components/transactions/transaction-filters";
import { TransactionForm } from "@/components/transactions/transaction-form";
import { TransactionRow } from "@/components/transactions/transaction-row";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { listAccounts, type Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { listCategories, type Category } from "@/lib/categories";
import {
  createTransaction,
  deleteTransaction,
  duplicateTransaction,
  listTransactions,
  updateTransaction,
  type Transaction,
  type TransactionFilters,
  type TransactionInput,
  type TransactionType,
  type TransactionUpdateInput,
} from "@/lib/transactions";

type ModalState =
  | { mode: "create"; initialType: TransactionType }
  | { mode: "edit"; transaction: Transaction }
  | { mode: "details"; transaction: Transaction }
  | null;

const PAGE_SIZE = 25;

const QUICK_ACTIONS: { type: TransactionType; label: string }[] = [
  { type: "expense", label: "+ Expense" },
  { type: "income", label: "+ Income" },
  { type: "transfer", label: "Transfer" },
];

export default function TransactionsPage() {
  const { accessToken } = useAuth();

  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [filters, setFilters] = useState<TransactionFilters>({
    sort_by: "occurred_at",
    sort_dir: "desc",
    limit: PAGE_SIZE,
    offset: 0,
  });

  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;
    void Promise.all([listAccounts(accessToken), listCategories(accessToken)]).then(
      ([accountsData, categoriesData]) => {
        if (!isMounted) return;
        setAccounts(accountsData);
        setCategories(categoriesData);
      }
    );
    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void listTransactions(accessToken, filters)
      .then((result) => {
        if (!isMounted) return;
        setTransactions(result.transactions);
        setTotal(result.total);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) setError(err instanceof ApiError ? err.message : "Failed to load transactions.");
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, filters, reloadToken]);

  async function handleCreate(input: TransactionInput | TransactionUpdateInput) {
    if (!accessToken) return;
    await createTransaction(accessToken, input as TransactionInput);
    setModalState(null);
    reload();
  }

  async function handleUpdate(transactionId: string, input: TransactionInput | TransactionUpdateInput) {
    if (!accessToken) return;
    await updateTransaction(accessToken, transactionId, input as TransactionUpdateInput);
    setModalState(null);
    reload();
  }

  async function handleDelete(transactionId: string) {
    if (!accessToken) return;
    await deleteTransaction(accessToken, transactionId);
    reload();
  }

  async function handleDuplicate(transactionId: string) {
    if (!accessToken) return;
    await duplicateTransaction(accessToken, transactionId);
    reload();
  }

  const accountsById = new Map((accounts ?? []).map((a) => [a.id, a]));
  const categoriesById = new Map((categories ?? []).map((c) => [c.id, c]));
  const isLoading = accounts === null || categories === null || transactions === null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Transactions</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Record, search, and manage everything you&apos;ve spent or earned.
          </p>
        </div>
        {accounts !== null && accounts.length > 0 && (
          <div className="flex gap-2">
            {QUICK_ACTIONS.map((action) => (
              <Button
                key={action.type}
                variant={action.type === "transfer" ? "secondary" : "primary"}
                onClick={() => setModalState({ mode: "create", initialType: action.type })}
              >
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </div>

      {accounts !== null && accounts.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            You need at least one account before you can record a transaction.
          </p>
          <a href="/accounts" className="mt-2 inline-block text-sm font-medium underline">
            Add an account
          </a>
        </div>
      )}

      {accounts !== null && accounts.length > 0 && categories !== null && (
        <>
          <QuickAddBar accounts={accounts} categories={categories} onCreated={reload} />
          <TransactionFiltersBar
            accounts={accounts}
            categories={categories}
            filters={filters}
            onChange={setFilters}
          />
        </>
      )}

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button type="button" onClick={reload} className="font-medium underline">
            Try again
          </button>
        </div>
      )}

      {isLoading && !error && (
        <div className="flex flex-col gap-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {!isLoading && transactions !== null && transactions.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            No transactions match your filters yet.
          </p>
        </div>
      )}

      {!isLoading && transactions !== null && transactions.length > 0 && (
        <Card>
          {transactions.map((transaction) => (
            <TransactionRow
              key={transaction.id}
              transaction={transaction}
              account={accountsById.get(transaction.account_id)}
              transferAccount={
                transaction.transfer_account_id
                  ? accountsById.get(transaction.transfer_account_id)
                  : undefined
              }
              category={transaction.category_id ? categoriesById.get(transaction.category_id) : undefined}
              onView={() => setModalState({ mode: "details", transaction })}
              onEdit={() => setModalState({ mode: "edit", transaction })}
              onDuplicate={() => handleDuplicate(transaction.id)}
              onDelete={() => handleDelete(transaction.id)}
            />
          ))}

          <div className="mt-4 flex items-center justify-between text-sm text-zinc-600 dark:text-zinc-400">
            <span>
              Showing {(filters.offset ?? 0) + 1}-
              {Math.min((filters.offset ?? 0) + (filters.limit ?? PAGE_SIZE), total)} of {total}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                disabled={(filters.offset ?? 0) === 0}
                onClick={() =>
                  setFilters((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - PAGE_SIZE) }))
                }
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                disabled={(filters.offset ?? 0) + (filters.limit ?? PAGE_SIZE) >= total}
                onClick={() => setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + PAGE_SIZE }))}
              >
                Next
              </Button>
            </div>
          </div>
        </Card>
      )}

      {modalState?.mode === "create" && accounts && categories && (
        <Modal
          title={modalState.initialType === "transfer" ? "Transfer money" : "Add transaction"}
          onClose={() => setModalState(null)}
        >
          <TransactionForm
            accounts={accounts}
            categories={categories}
            initial={{ type: modalState.initialType }}
            onSubmit={handleCreate}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}

      {modalState?.mode === "edit" && accounts && categories && (
        <Modal title="Edit transaction" onClose={() => setModalState(null)}>
          <TransactionForm
            accounts={accounts}
            categories={categories}
            transaction={modalState.transaction}
            onSubmit={(input) => handleUpdate(modalState.transaction.id, input)}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}

      {modalState?.mode === "details" && (
        <Modal title="Transaction details" onClose={() => setModalState(null)}>
          <TransactionDetails
            transaction={modalState.transaction}
            account={accountsById.get(modalState.transaction.account_id)}
            transferAccount={
              modalState.transaction.transfer_account_id
                ? accountsById.get(modalState.transaction.transfer_account_id)
                : undefined
            }
            category={
              modalState.transaction.category_id
                ? categoriesById.get(modalState.transaction.category_id)
                : undefined
            }
            onEdit={() => setModalState({ mode: "edit", transaction: modalState.transaction })}
            onDuplicate={async () => {
              await handleDuplicate(modalState.transaction.id);
              setModalState(null);
            }}
            onDelete={async () => {
              await handleDelete(modalState.transaction.id);
              setModalState(null);
            }}
          />
        </Modal>
      )}
    </div>
  );
}
