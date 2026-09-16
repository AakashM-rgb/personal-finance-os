"use client";

import { useEffect, useState } from "react";

import { RecurringTransactionCard } from "@/components/recurring-transactions/recurring-transaction-card";
import { RecurringTransactionForm } from "@/components/recurring-transactions/recurring-transaction-form";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { listAccounts, type Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { listCategories, type Category } from "@/lib/categories";
import {
  createRecurringTransaction,
  deactivateRecurringTransaction,
  generateRecurringTransactions,
  listRecurringTransactions,
  updateRecurringTransaction,
  type RecurringTransaction,
  type RecurringTransactionCreateInput,
  type RecurringTransactionUpdateInput,
} from "@/lib/recurring-transactions";

type ModalState =
  | { mode: "create" }
  | { mode: "edit"; recurring: RecurringTransaction }
  | null;

export default function RecurringTransactionsPage() {
  const { accessToken } = useAuth();

  const [items, setItems] = useState<RecurringTransaction[] | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateMessage, setGenerateMessage] = useState<string | null>(null);

  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void Promise.all([
      listRecurringTransactions(accessToken),
      listAccounts(accessToken),
      listCategories(accessToken),
    ])
      .then(([itemsData, accountsData, categoriesData]) => {
        if (!isMounted) return;
        setItems(itemsData);
        setAccounts(accountsData);
        setCategories(categoriesData);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof ApiError ? err.message : "Failed to load recurring transactions.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  async function handleCreate(
    input: RecurringTransactionCreateInput | RecurringTransactionUpdateInput
  ) {
    if (!accessToken) return;
    await createRecurringTransaction(accessToken, input as RecurringTransactionCreateInput);
    setModalState(null);
    reload();
  }

  async function handleUpdate(
    recurringId: string,
    input: RecurringTransactionCreateInput | RecurringTransactionUpdateInput
  ) {
    if (!accessToken) return;
    await updateRecurringTransaction(accessToken, recurringId, input as RecurringTransactionUpdateInput);
    setModalState(null);
    reload();
  }

  async function handleDeactivate(recurringId: string) {
    if (!accessToken) return;
    await deactivateRecurringTransaction(accessToken, recurringId);
    reload();
  }

  async function handleGenerate() {
    if (!accessToken) return;
    setIsGenerating(true);
    setGenerateMessage(null);
    try {
      const generated = await generateRecurringTransactions(accessToken);
      setGenerateMessage(
        generated.length === 0
          ? "Nothing new to generate - you're all caught up."
          : `Generated ${generated.length} transaction${generated.length === 1 ? "" : "s"}.`
      );
      reload();
    } catch (err) {
      setGenerateMessage(
        err instanceof ApiError ? err.message : "Failed to generate transactions."
      );
    } finally {
      setIsGenerating(false);
    }
  }

  const isLoading = items === null && !error;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
            Recurring Transactions
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Set up bills and income that repeat on a schedule.
          </p>
        </div>
        {!isLoading && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" isLoading={isGenerating} onClick={() => void handleGenerate()}>
              Generate now
            </Button>
            <Button onClick={() => setModalState({ mode: "create" })}>+ Add recurring</Button>
          </div>
        )}
      </div>

      {generateMessage && (
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
          {generateMessage}
        </div>
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      )}

      {!isLoading && items !== null && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            You haven&apos;t set up any recurring transactions yet.
          </p>
          <Button className="mt-4" onClick={() => setModalState({ mode: "create" })}>
            + Add your first recurring transaction
          </Button>
        </div>
      )}

      {!isLoading && items !== null && items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <RecurringTransactionCard
              key={item.id}
              recurring={item}
              onEdit={() => setModalState({ mode: "edit", recurring: item })}
              onDeactivate={() => handleDeactivate(item.id)}
            />
          ))}
        </div>
      )}

      {modalState?.mode === "create" && accounts !== null && categories !== null && (
        <Modal title="Add recurring transaction" onClose={() => setModalState(null)}>
          <RecurringTransactionForm
            accounts={accounts}
            categories={categories}
            onSubmit={handleCreate}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}

      {modalState?.mode === "edit" && accounts !== null && categories !== null && (
        <Modal title="Edit recurring transaction" onClose={() => setModalState(null)}>
          <RecurringTransactionForm
            recurring={modalState.recurring}
            accounts={accounts}
            categories={categories}
            onSubmit={(input) => handleUpdate(modalState.recurring.id, input)}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}
    </div>
  );
}
