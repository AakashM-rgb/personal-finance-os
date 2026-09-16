import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { Receipt } from "@/lib/receipts";

const STATUS_STYLES: Record<Receipt["status"], string> = {
  pending: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  processed: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  confirmed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
};

const STATUS_LABELS: Record<Receipt["status"], string> = {
  pending: "Pending",
  processed: "Needs review",
  confirmed: "Confirmed",
  failed: "OCR failed",
};

export function ReceiptCard({ receipt, onClick }: { receipt: Receipt; onClick: () => void }) {
  const merchant =
    receipt.confirmed_merchant ?? receipt.extraction?.merchant ?? receipt.original_filename ?? "Receipt";
  const totalMinor = receipt.confirmed_total_minor ?? receipt.extraction?.total_minor ?? null;
  const date = receipt.confirmed_date ?? receipt.extraction?.date;

  return (
    <button type="button" onClick={onClick} className="text-left">
      <Card className="flex h-full flex-col gap-3 transition-shadow hover:shadow-md">
        <div className="flex items-start justify-between gap-2">
          <p className="font-medium text-zinc-900 dark:text-zinc-50">{merchant}</p>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[receipt.status]}`}
          >
            {STATUS_LABELS[receipt.status]}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm text-zinc-600 dark:text-zinc-400">
          <span>{date ?? "No date"}</span>
          <span className="font-medium text-zinc-900 dark:text-zinc-50">
            {totalMinor !== null ? formatMoney(totalMinor) : "—"}
          </span>
        </div>
        {receipt.transaction_id && (
          <p className="text-xs text-emerald-700 dark:text-emerald-400">Linked to a transaction</p>
        )}
      </Card>
    </button>
  );
}
