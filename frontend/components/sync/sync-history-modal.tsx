"use client";

import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { listSyncRuns, type LinkedAccount, type SyncRun, type SyncRunStatus } from "@/lib/sync";

const RUN_STATUS_LABEL: Record<SyncRunStatus, string> = {
  success: "Completed",
  partial: "Partially completed",
  failed: "Failed",
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

interface SyncHistoryModalProps {
  accessToken: string;
  linkedAccount: LinkedAccount;
  onClose: () => void;
}

export function SyncHistoryModal({ accessToken, linkedAccount, onClose }: SyncHistoryModalProps) {
  const [runs, setRuns] = useState<SyncRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    void listSyncRuns(accessToken, linkedAccount.id)
      .then((data) => {
        if (!isMounted) return;
        setRuns(data);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof ApiError ? err.message : "Failed to load sync history.");
        }
      });
    return () => {
      isMounted = false;
    };
  }, [accessToken, linkedAccount.id]);

  return (
    <Modal title={`Sync history · ${linkedAccount.external_institution_name}`} onClose={onClose}>
      <div className="flex max-h-96 flex-col gap-3 overflow-y-auto">
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        {runs === null && !error && (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        )}

        {runs !== null && runs.length === 0 && (
          <p className="py-4 text-center text-sm text-zinc-600 dark:text-zinc-400">
            No sync history yet.
          </p>
        )}

        {runs !== null &&
          runs.map((run) => (
            <div
              key={run.id}
              className="rounded-md border border-zinc-200 p-3 text-xs dark:border-zinc-800"
            >
              <div className="flex items-center justify-between">
                <span className={`font-medium ${RUN_STATUS_COLOR[run.status]}`}>
                  {RUN_STATUS_LABEL[run.status]}
                </span>
                <span className="text-zinc-500 dark:text-zinc-400">
                  {formatDateTime(run.started_at)}
                </span>
              </div>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">
                {run.transactions_fetched} found · {run.transactions_created} imported ·{" "}
                {run.transactions_skipped_duplicate} skipped
              </p>
              {run.error_message && (
                <p className="mt-1 text-red-600 dark:text-red-400">{run.error_message}</p>
              )}
            </div>
          ))}
      </div>
    </Modal>
  );
}
