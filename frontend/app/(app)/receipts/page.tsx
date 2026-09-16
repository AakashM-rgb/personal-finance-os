"use client";

import { useEffect, useState } from "react";

import { ReceiptCard } from "@/components/receipts/receipt-card";
import { ReceiptDetailModal } from "@/components/receipts/receipt-detail-modal";
import { ReceiptUpload } from "@/components/receipts/receipt-upload";
import { Skeleton } from "@/components/ui/skeleton";
import { listAccounts, type Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { listCategories, type Category } from "@/lib/categories";
import { listReceipts, type Receipt } from "@/lib/receipts";

export default function ReceiptsPage() {
  const { accessToken } = useAuth();

  const [receipts, setReceipts] = useState<Receipt[] | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void Promise.all([listReceipts(accessToken), listAccounts(accessToken), listCategories(accessToken)])
      .then(([receiptsData, accountsData, categoriesData]) => {
        if (!isMounted) return;
        setReceipts(receiptsData);
        setAccounts(accountsData);
        setCategories(categoriesData);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof ApiError ? err.message : "Failed to load receipts.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  function handleUploaded(receipt: Receipt) {
    setReceipts((prev) => (prev ? [receipt, ...prev] : [receipt]));
    setSelectedId(receipt.id);
  }

  function handleChanged(receipt: Receipt) {
    setReceipts((prev) => prev?.map((r) => (r.id === receipt.id ? receipt : r)) ?? prev);
  }

  function handleDeleted(receiptId: string) {
    setReceipts((prev) => prev?.filter((r) => r.id !== receiptId) ?? prev);
    setSelectedId(null);
  }

  const isLoading = receipts === null && !error;
  const selected = receipts?.find((r) => r.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Receipts</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Scan a receipt, review what was found, and attach it to a transaction.
        </p>
      </div>

      {accessToken && <ReceiptUpload accessToken={accessToken} onUploaded={handleUploaded} />}

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
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {!isLoading && receipts !== null && receipts.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            You haven&apos;t uploaded any receipts yet.
          </p>
        </div>
      )}

      {!isLoading && receipts !== null && receipts.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {receipts.map((receipt) => (
            <ReceiptCard key={receipt.id} receipt={receipt} onClick={() => setSelectedId(receipt.id)} />
          ))}
        </div>
      )}

      {selected && accounts !== null && categories !== null && accessToken && (
        <ReceiptDetailModal
          receipt={selected}
          accounts={accounts}
          categories={categories}
          accessToken={accessToken}
          onClose={() => setSelectedId(null)}
          onChanged={handleChanged}
          onDeleted={handleDeleted}
        />
      )}
    </div>
  );
}
