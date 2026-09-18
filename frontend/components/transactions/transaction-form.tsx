"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import type { Category } from "@/lib/categories";
import { minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";
import type {
  Transaction,
  TransactionInput,
  TransactionType,
  TransactionUpdateInput,
} from "@/lib/transactions";

interface TransactionFormProps {
  accounts: Account[];
  categories: Category[];
  transaction?: Transaction;
  initial?: Partial<TransactionInput>;
  onSubmit: (input: TransactionInput | TransactionUpdateInput) => Promise<void>;
  onCancel: () => void;
}

function toDatetimeLocal(iso?: string): string {
  const date = iso ? new Date(iso) : new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

export function TransactionForm({
  accounts,
  categories,
  transaction,
  initial,
  onSubmit,
  onCancel,
}: TransactionFormProps) {
  const isEditing = transaction !== undefined;

  const [type, setType] = useState<TransactionType>(transaction?.type ?? initial?.type ?? "expense");
  const [accountId, setAccountId] = useState(
    transaction?.account_id ?? initial?.account_id ?? accounts[0]?.id ?? ""
  );
  const [transferAccountId, setTransferAccountId] = useState(
    transaction?.transfer_account_id ?? ""
  );
  const [categoryId, setCategoryId] = useState(transaction?.category_id ?? initial?.category_id ?? "");

  const selectedAccount = accounts.find((a) => a.id === accountId);
  const currency = selectedAccount?.currency ?? "INR";

  const [amountInput, setAmountInput] = useState(
    transaction
      ? minorUnitsToInputValue(transaction.amount_minor, transaction.currency)
      : initial?.amount_minor != null
        ? minorUnitsToInputValue(initial.amount_minor, currency)
        : ""
  );
  const [merchant, setMerchant] = useState(transaction?.merchant ?? "");
  const [description, setDescription] = useState(transaction?.description ?? initial?.description ?? "");
  const [notes, setNotes] = useState(transaction?.notes ?? "");
  const [paymentMethod, setPaymentMethod] = useState(transaction?.payment_method ?? "");
  const [tagsInput, setTagsInput] = useState((transaction?.tags ?? []).join(", "));
  const [occurredAt, setOccurredAt] = useState(toDatetimeLocal(transaction?.occurred_at));
  const [isRecurring, setIsRecurring] = useState(transaction?.is_recurring ?? false);
  // Opt-in only, per edit - never pre-checked, so a plain save never
  // silently creates or changes a merchant rule (see
  // app.services.merchant_rule_service / TransactionUpdate.remember_category_for_merchant).
  const [rememberCategory, setRememberCategory] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isTransfer = type === "transfer";
  const canRememberCategory = isEditing && !isTransfer && merchant.trim() !== "" && categoryId !== "";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    const amountMinor = parseMoneyToMinorUnits(amountInput, currency);
    if (amountMinor === null || amountMinor <= 0) {
      setFieldErrors({ amount: "Enter an amount greater than zero." });
      return;
    }

    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    const payload: TransactionInput = {
      account_id: accountId,
      type,
      amount_minor: amountMinor,
      transfer_account_id: isTransfer ? transferAccountId || null : null,
      category_id: isTransfer ? null : categoryId || null,
      merchant: merchant || null,
      description: description || null,
      notes: notes || null,
      payment_method: paymentMethod || null,
      tags,
      occurred_at: new Date(occurredAt).toISOString(),
      is_recurring: isRecurring,
    };

    setIsSubmitting(true);
    try {
      if (isEditing) {
        await onSubmit({
          ...payload,
          clear_category: isTransfer || !categoryId,
          remember_category_for_merchant: canRememberCategory && rememberCategory,
        });
      } else {
        await onSubmit(payload);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors ?? {});
        if (!err.fieldErrors) setError(err.message);
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
      <div className="grid grid-cols-3 gap-2">
        {(["expense", "income", "transfer"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setType(t)}
            className={`rounded-md border px-3 py-2 text-sm font-medium capitalize ${
              type === t
                ? "border-zinc-900 bg-zinc-900 text-white dark:border-white dark:bg-white dark:text-zinc-900"
                : "border-zinc-300 text-zinc-700 dark:border-zinc-700 dark:text-zinc-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="txn-amount">Amount ({currency})</Label>
          <Input
            id="txn-amount"
            inputMode="decimal"
            required
            value={amountInput}
            onChange={(e) => setAmountInput(e.target.value)}
          />
          <FormError message={fieldErrors.amount ?? null} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="txn-date">Date &amp; time</Label>
          <Input
            id="txn-date"
            type="datetime-local"
            required
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="txn-account">{isTransfer ? "From account" : "Account"}</Label>
        <Select id="txn-account" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name} ({account.currency})
            </option>
          ))}
        </Select>
      </div>

      {isTransfer ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="txn-transfer-account">To account</Label>
          <Select
            id="txn-transfer-account"
            value={transferAccountId}
            onChange={(e) => setTransferAccountId(e.target.value)}
          >
            <option value="">Select destination account</option>
            {accounts
              .filter((a) => a.id !== accountId)
              .map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name} ({account.currency})
                </option>
              ))}
          </Select>
          <FormError message={fieldErrors.transfer_account_id ?? null} />
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="txn-category">Category (optional)</Label>
          <Select id="txn-category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">No category</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.icon} {category.name}
              </option>
            ))}
          </Select>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="txn-description">Description</Label>
        <Input
          id="txn-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      {!isTransfer && (
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="txn-merchant">Merchant (optional)</Label>
            <Input
              id="txn-merchant"
              value={merchant}
              onChange={(e) => setMerchant(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="txn-payment-method">Payment method (optional)</Label>
            <Input
              id="txn-payment-method"
              value={paymentMethod}
              onChange={(e) => setPaymentMethod(e.target.value)}
            />
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="txn-tags">Tags (comma-separated, optional)</Label>
        <Input id="txn-tags" value={tagsInput} onChange={(e) => setTagsInput(e.target.value)} />
      </div>

      {!isTransfer && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="txn-notes">Notes (optional)</Label>
          <textarea
            id="txn-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </div>
      )}

      {!isTransfer && (
        <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
          <input
            type="checkbox"
            checked={isRecurring}
            onChange={(e) => setIsRecurring(e.target.checked)}
          />
          This is a recurring bill or income
        </label>
      )}

      {canRememberCategory && (
        <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
          <input
            type="checkbox"
            checked={rememberCategory}
            onChange={(e) => setRememberCategory(e.target.checked)}
          />
          Remember this category for &quot;{merchant.trim()}&quot;
        </label>
      )}

      <FormError message={error} />

      <div className="mt-2 flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isSubmitting}>
          {isEditing ? "Save changes" : "Add transaction"}
        </Button>
      </div>
    </form>
  );
}
