"use client";

import { useEffect, useState } from "react";

import { AccountCard } from "@/components/accounts/account-card";
import { AccountForm } from "@/components/accounts/account-form";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import {
  archiveAccount,
  createAccount,
  listAccounts,
  updateAccount,
  type Account,
  type AccountCreateInput,
  type AccountUpdateInput,
} from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";

type ModalState = { mode: "create" } | { mode: "edit"; account: Account } | null;

export default function AccountsPage() {
  const { accessToken } = useAuth();
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void listAccounts(accessToken)
      .then((data) => {
        if (!isMounted) return;
        setAccounts(data);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) setError(err instanceof ApiError ? err.message : "Failed to load accounts.");
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  async function handleCreate(input: AccountCreateInput | AccountUpdateInput) {
    if (!accessToken) return;
    await createAccount(accessToken, input as AccountCreateInput);
    setModalState(null);
    reload();
  }

  async function handleUpdate(accountId: string, input: AccountCreateInput | AccountUpdateInput) {
    if (!accessToken) return;
    await updateAccount(accessToken, accountId, input as AccountUpdateInput);
    setModalState(null);
    reload();
  }

  async function handleDelete(accountId: string) {
    if (!accessToken) return;
    await archiveAccount(accessToken, accountId);
    reload();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Accounts</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Bank accounts, cash, cards, and wallets in one place.
          </p>
        </div>
        <Button className="self-start sm:self-auto" onClick={() => setModalState({ mode: "create" })}>
          + Add account
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button
            type="button"
            onClick={reload}
            className="font-medium underline"
          >
            Try again
          </button>
        </div>
      )}

      {accounts === null && !error && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      )}

      {accounts !== null && accounts.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            You haven&apos;t added any accounts yet.
          </p>
          <Button className="mt-4" onClick={() => setModalState({ mode: "create" })}>
            + Add your first account
          </Button>
        </div>
      )}

      {accounts !== null && accounts.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {accounts.map((account) => (
            <AccountCard
              key={account.id}
              account={account}
              onEdit={() => setModalState({ mode: "edit", account })}
              onDelete={() => handleDelete(account.id)}
            />
          ))}
        </div>
      )}

      {modalState?.mode === "create" && (
        <Modal title="Add account" onClose={() => setModalState(null)}>
          <AccountForm onSubmit={handleCreate} onCancel={() => setModalState(null)} />
        </Modal>
      )}

      {modalState?.mode === "edit" && (
        <Modal title="Edit account" onClose={() => setModalState(null)}>
          <AccountForm
            account={modalState.account}
            onSubmit={(input) => handleUpdate(modalState.account.id, input)}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}
    </div>
  );
}
