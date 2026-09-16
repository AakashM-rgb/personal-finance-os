"use client";

import { useEffect, useState } from "react";

import { BudgetCard } from "@/components/budgets/budget-card";
import { BudgetForm } from "@/components/budgets/budget-form";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { listAccounts, type Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import {
  createBudget,
  deleteBudget,
  listBudgetSuggestions,
  listBudgets,
  updateBudget,
  type Budget,
  type BudgetCreateInput,
  type BudgetSuggestion,
  type BudgetUpdateInput,
} from "@/lib/budgets";
import { listCategories, type Category } from "@/lib/categories";

type ModalState = { mode: "create" } | { mode: "edit"; budget: Budget } | null;

export default function BudgetsPage() {
  const { accessToken } = useAuth();

  const [budgets, setBudgets] = useState<Budget[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [suggestions, setSuggestions] = useState<BudgetSuggestion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void Promise.all([
      listBudgets(accessToken),
      listCategories(accessToken),
      listAccounts(accessToken),
      listBudgetSuggestions(accessToken),
    ])
      .then(([budgetsData, categoriesData, accountsData, suggestionsData]) => {
        if (!isMounted) return;
        setBudgets(budgetsData);
        setCategories(categoriesData);
        setAccounts(accountsData);
        setSuggestions(suggestionsData);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) setError(err instanceof ApiError ? err.message : "Failed to load budgets.");
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  async function handleCreate(input: BudgetCreateInput | BudgetUpdateInput) {
    if (!accessToken) return;
    await createBudget(accessToken, input as BudgetCreateInput);
    setModalState(null);
    reload();
  }

  async function handleUpdate(budgetId: string, input: BudgetCreateInput | BudgetUpdateInput) {
    if (!accessToken) return;
    await updateBudget(accessToken, budgetId, input as BudgetUpdateInput);
    setModalState(null);
    reload();
  }

  async function handleDelete(budgetId: string) {
    if (!accessToken) return;
    await deleteBudget(accessToken, budgetId);
    reload();
  }

  const isLoading = budgets === null && !error;
  const budgetedCategoryIds = new Set((budgets ?? []).map((b) => b.category_id));
  const availableCategories = (categories ?? []).filter((c) => !budgetedCategoryIds.has(c.id));
  const currency = budgets?.[0]?.currency ?? accounts?.[0]?.currency ?? "INR";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Budgets</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Set a monthly limit per category and track how you&apos;re doing.
          </p>
        </div>
        {!isLoading && availableCategories.length > 0 && (
          <Button className="self-start sm:self-auto" onClick={() => setModalState({ mode: "create" })}>
            + Add budget
          </Button>
        )}
      </div>

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

      {!isLoading && budgets !== null && budgets.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            You haven&apos;t set any budgets yet.
          </p>
          <Button className="mt-4" onClick={() => setModalState({ mode: "create" })}>
            + Add your first budget
          </Button>
        </div>
      )}

      {!isLoading && budgets !== null && budgets.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {budgets.map((budget) => (
            <BudgetCard
              key={budget.id}
              budget={budget}
              currency={currency}
              onEdit={() => setModalState({ mode: "edit", budget })}
              onDelete={() => handleDelete(budget.id)}
            />
          ))}
        </div>
      )}

      {modalState?.mode === "create" && categories !== null && (
        <Modal title="Add budget" onClose={() => setModalState(null)}>
          <BudgetForm
            availableCategories={availableCategories}
            suggestions={suggestions}
            currency={currency}
            onSubmit={handleCreate}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}

      {modalState?.mode === "edit" && (
        <Modal title="Edit budget" onClose={() => setModalState(null)}>
          <BudgetForm
            budget={modalState.budget}
            availableCategories={availableCategories}
            currency={currency}
            onSubmit={(input) => handleUpdate(modalState.budget.id, input)}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}
    </div>
  );
}
