"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormError } from "@/components/ui/form-error";
import { ApiError } from "@/lib/api-client";
import type { LinkedAccount, SyncConsentStatus, SyncRun, SyncRunStatus } from "@/lib/sync";

const STATUS_LABEL: Record<SyncConsentStatus, string> = {
  pending: "Pending",
  active: "Active",
  paused: "Paused",
  revoked: "Disconnected",
  expired: "Expired",
};

const STATUS_COLOR: Record<SyncConsentStatus, string> = {
  pending: "text-amber-600 dark:text-amber-400",
  active: "text-emerald-600 dark:text-emerald-400",
  paused: "text-amber-600 dark:text-amber-400",
  revoked: "text-zinc-500 dark:text-zinc-400",
  expired: "text-red-600 dark:text-red-400",
};

const RUN_STATUS_LABEL: Record<SyncRunStatus, string> = {
  success: "Sync completed",
  partial: "Sync partially completed",
  failed: "Sync failed",
};

const RUN_STATUS_COLOR: Record<SyncRunStatus, string> = {
  success: "text-emerald-600 dark:text-emerald-400",
  partial: "text-amber-600 dark:text-amber-400",
  failed: "text-red-600 dark:text-red-400",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface LinkedAccountCardProps {
  linkedAccount: LinkedAccount;
  onSync: (linkedAccountId: string) => Promise<SyncRun>;
  onRequestDisconnect: () => void;
  onViewHistory: () => void;
}

export function LinkedAccountCard({
  linkedAccount,
  onSync,
  onRequestDisconnect,
  onViewHistory,
}: LinkedAccountCardProps) {
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<SyncRun | null>(null);

  const isActive = linkedAccount.consent_status === "active";

  async function handleSyncNow() {
    setIsSyncing(true);
    setSyncError(null);
    try {
      const result = await onSync(linkedAccount.id);
      setLastResult(result);
    } catch (err) {
      setSyncError(err instanceof ApiError ? err.message : "Sync failed. Please try again.");
    } finally {
      setIsSyncing(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl" aria-hidden="true">
            🏦
          </span>
          <div>
            <p className="font-medium text-zinc-900 dark:text-zinc-50">
              {linkedAccount.external_institution_name}
            </p>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {linkedAccount.masked_account_ref ?? "No account reference"}
            </p>
          </div>
        </div>
        <span
          className={`shrink-0 text-xs font-medium ${STATUS_COLOR[linkedAccount.consent_status]}`}
        >
          {STATUS_LABEL[linkedAccount.consent_status]}
        </span>
      </div>

      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        {linkedAccount.last_synced_at
          ? `Last synced ${formatDateTime(linkedAccount.last_synced_at)}`
          : "Never synced"}
      </p>

      <FormError message={syncError} />

      {lastResult && (
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
          <p className={`font-medium ${RUN_STATUS_COLOR[lastResult.status]}`}>
            {RUN_STATUS_LABEL[lastResult.status]}
          </p>
          <p className="mt-1">
            {lastResult.transactions_fetched} found · {lastResult.transactions_created} imported ·{" "}
            {lastResult.transactions_skipped_duplicate} already synced
          </p>
          {lastResult.error_message && (
            <p className="mt-1 text-red-600 dark:text-red-400">{lastResult.error_message}</p>
          )}
        </div>
      )}

      <div className="mt-1 flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onViewHistory}>
          History
        </Button>
        {isActive && (
          <Button variant="secondary" isLoading={isSyncing} onClick={() => void handleSyncNow()}>
            Sync Now
          </Button>
        )}
        {linkedAccount.consent_status !== "revoked" && (
          <Button variant="ghost" onClick={onRequestDisconnect} disabled={isSyncing}>
            Disconnect
          </Button>
        )}
      </div>
    </Card>
  );
}
