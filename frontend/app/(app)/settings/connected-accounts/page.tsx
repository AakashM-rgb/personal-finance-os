"use client";

import { useEffect, useState } from "react";

import { ConnectAccountModal } from "@/components/sync/connect-account-modal";
import { LinkedAccountCard } from "@/components/sync/linked-account-card";
import { SyncHistoryModal } from "@/components/sync/sync-history-modal";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { listLinkedAccounts, revokeLink, triggerSync, type LinkedAccount, type SyncRun } from "@/lib/sync";

type ModalState =
  | { mode: "connect" }
  | { mode: "disconnect"; linkedAccount: LinkedAccount }
  | { mode: "history"; linkedAccount: LinkedAccount }
  | null;

export default function ConnectedAccountsPage() {
  const { accessToken } = useAuth();
  const [linkedAccounts, setLinkedAccounts] = useState<LinkedAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [disconnectError, setDisconnectError] = useState<string | null>(null);

  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void listLinkedAccounts(accessToken)
      .then((data) => {
        if (!isMounted) return;
        setLinkedAccounts(data);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof ApiError ? err.message : "Failed to load connected accounts.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  async function handleSync(linkedAccountId: string): Promise<SyncRun> {
    if (!accessToken) throw new Error("Not authenticated.");
    const result = await triggerSync(accessToken, linkedAccountId);
    // Refreshes last_synced_at/last_sync_status on the card, and makes any
    // newly imported transaction visible the next time the Transactions
    // page (the single source of truth) is opened - never a second,
    // frontend-only copy of the ledger.
    reload();
    return result;
  }

  async function handleDisconnect(linkedAccountId: string) {
    if (!accessToken) return;
    setIsDisconnecting(true);
    setDisconnectError(null);
    try {
      await revokeLink(accessToken, linkedAccountId);
      setModalState(null);
      reload();
    } catch (err) {
      setDisconnectError(err instanceof ApiError ? err.message : "Failed to disconnect. Please try again.");
    } finally {
      setIsDisconnecting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
            Connected Accounts
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Automatically import transactions from linked financial accounts.
          </p>
        </div>
        {linkedAccounts !== null && linkedAccounts.length > 0 && (
          <Button
            className="self-start sm:self-auto"
            onClick={() => setModalState({ mode: "connect" })}
          >
            + Connect Financial Account
          </Button>
        )}
      </div>

      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        🔒 Read-only transaction access. Your finance app can import transaction data but cannot
        make payments or move money.
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button type="button" onClick={reload} className="font-medium underline">
            Try again
          </button>
        </div>
      )}

      {linkedAccounts === null && !error && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      )}

      {linkedAccounts !== null && linkedAccounts.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            No financial accounts connected.
          </p>
          <Button className="mt-4" onClick={() => setModalState({ mode: "connect" })}>
            + Connect Financial Account
          </Button>
        </div>
      )}

      {linkedAccounts !== null && linkedAccounts.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {linkedAccounts.map((linkedAccount) => (
            <LinkedAccountCard
              key={linkedAccount.id}
              linkedAccount={linkedAccount}
              onSync={handleSync}
              onRequestDisconnect={() => setModalState({ mode: "disconnect", linkedAccount })}
              onViewHistory={() => setModalState({ mode: "history", linkedAccount })}
            />
          ))}
        </div>
      )}

      {modalState?.mode === "connect" && accessToken && (
        <ConnectAccountModal
          accessToken={accessToken}
          onConnected={() => {
            setModalState(null);
            reload();
          }}
          onCancel={() => setModalState(null)}
        />
      )}

      {modalState?.mode === "disconnect" && (
        <Modal title="Disconnect account" onClose={() => setModalState(null)}>
          <div className="flex flex-col gap-4">
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Disconnecting <strong>{modalState.linkedAccount.external_institution_name}</strong>{" "}
              stops future synchronization. Previously imported transactions remain in your
              finance app and are never deleted.
            </p>
            <FormError message={disconnectError} />
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => setModalState(null)}
                disabled={isDisconnecting}
              >
                Cancel
              </Button>
              <Button
                className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
                isLoading={isDisconnecting}
                onClick={() => void handleDisconnect(modalState.linkedAccount.id)}
              >
                Disconnect
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {modalState?.mode === "history" && accessToken && (
        <SyncHistoryModal
          accessToken={accessToken}
          linkedAccount={modalState.linkedAccount}
          onClose={() => setModalState(null)}
        />
      )}
    </div>
  );
}
