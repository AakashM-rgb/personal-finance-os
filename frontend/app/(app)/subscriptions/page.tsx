"use client";

import { useEffect, useState } from "react";

import { SubscriptionCard } from "@/components/subscriptions/subscription-card";
import { SubscriptionForm } from "@/components/subscriptions/subscription-form";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { listAccounts, type Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { listCategories, type Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import {
  calculateActiveTotals,
  createSubscription,
  deactivateSubscription,
  listSubscriptions,
  updateSubscription,
  type Subscription,
  type SubscriptionCreateInput,
  type SubscriptionUpdateInput,
} from "@/lib/subscriptions";

type ModalState = { mode: "create" } | { mode: "edit"; subscription: Subscription } | null;

export default function SubscriptionsPage() {
  const { accessToken } = useAuth();

  const [items, setItems] = useState<Subscription[] | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void Promise.all([
      listSubscriptions(accessToken),
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
          setError(err instanceof ApiError ? err.message : "Failed to load subscriptions.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  async function handleCreate(input: SubscriptionCreateInput | SubscriptionUpdateInput) {
    if (!accessToken) return;
    await createSubscription(accessToken, input as SubscriptionCreateInput);
    setModalState(null);
    reload();
  }

  async function handleUpdate(
    subscriptionId: string,
    input: SubscriptionCreateInput | SubscriptionUpdateInput
  ) {
    if (!accessToken) return;
    await updateSubscription(accessToken, subscriptionId, input as SubscriptionUpdateInput);
    setModalState(null);
    reload();
  }

  async function handleDeactivate(subscriptionId: string) {
    if (!accessToken) return;
    await deactivateSubscription(accessToken, subscriptionId);
    reload();
  }

  const isLoading = items === null && !error;
  const activeItems = (items ?? []).filter((item) => item.is_active);
  const currency = activeItems[0]?.currency ?? accounts?.[0]?.currency ?? "INR";
  const { monthlyTotal, yearlyTotal } = calculateActiveTotals(items ?? []);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Subscriptions</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Track recurring bills and see what they really cost you.
          </p>
        </div>
        {!isLoading && (
          <Button className="self-start sm:self-auto" onClick={() => setModalState({ mode: "create" })}>
            + Add subscription
          </Button>
        )}
      </div>

      {!isLoading && activeItems.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Monthly</p>
            <p className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
              {formatMoney(monthlyTotal, currency)}
            </p>
          </Card>
          <Card>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Yearly</p>
            <p className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
              {formatMoney(yearlyTotal, currency)}
            </p>
          </Card>
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
            You haven&apos;t added any subscriptions yet.
          </p>
          <Button className="mt-4" onClick={() => setModalState({ mode: "create" })}>
            + Add your first subscription
          </Button>
        </div>
      )}

      {!isLoading && items !== null && items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <SubscriptionCard
              key={item.id}
              subscription={item}
              onEdit={() => setModalState({ mode: "edit", subscription: item })}
              onDeactivate={() => handleDeactivate(item.id)}
            />
          ))}
        </div>
      )}

      {modalState?.mode === "create" && accounts !== null && categories !== null && (
        <Modal title="Add subscription" onClose={() => setModalState(null)}>
          <SubscriptionForm
            accounts={accounts}
            categories={categories}
            onSubmit={handleCreate}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}

      {modalState?.mode === "edit" && accounts !== null && categories !== null && (
        <Modal title="Edit subscription" onClose={() => setModalState(null)}>
          <SubscriptionForm
            subscription={modalState.subscription}
            accounts={accounts}
            categories={categories}
            onSubmit={(input) => handleUpdate(modalState.subscription.id, input)}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}
    </div>
  );
}
