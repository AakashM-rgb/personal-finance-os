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
import {
  FREQUENCY_LABELS,
  RECURRENCE_FREQUENCIES,
  type RecurringTransaction,
  type RecurringTransactionCreateInput,
  type RecurringTransactionUpdateInput,
} from "@/lib/recurring-transactions";

interface RecurringTransactionFormProps {
  recurring?: RecurringTransaction;
  accounts: Account[];
  categories: Category[];
  onSubmit: (
    input: RecurringTransactionCreateInput | RecurringTransactionUpdateInput
  ) => Promise<void>;
  onCancel: () => void;
}

const NO_CATEGORY = "__none__";

export function RecurringTransactionForm({
  recurring,
  accounts,
  categories,
  onSubmit,
  onCancel,
}: RecurringTransactionFormProps) {
  const isEditing = recurring !== undefined;
  const currency = recurring?.currency ?? accounts[0]?.currency ?? "INR";

  const [name, setName] = useState(recurring?.name ?? "");
  const [accountId, setAccountId] = useState(recurring?.account_id ?? accounts[0]?.id ?? "");
  const [categoryId, setCategoryId] = useState(recurring?.category_id ?? NO_CATEGORY);
  const [type, setType] = useState<"income" | "expense">(recurring?.type ?? "expense");
  const [amountInput, setAmountInput] = useState(
    recurring ? minorUnitsToInputValue(recurring.amount_minor, currency) : ""
  );
  const [frequency, setFrequency] = useState(recurring?.frequency ?? "monthly");
  const [startDate, setStartDate] = useState(
    recurring?.start_date ?? new Date().toISOString().slice(0, 10)
  );
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    const amountMinor = parseMoneyToMinorUnits(amountInput, currency);
    const nextFieldErrors: Record<string, string> = {};
    if (!name.trim()) nextFieldErrors.name = "Enter a name.";
    if (!isEditing && !accountId) nextFieldErrors.account_id = "Choose an account.";
    if (amountMinor === null || amountMinor <= 0) {
      nextFieldErrors.amount = "Enter an amount greater than zero.";
    }
    if (!isEditing && !startDate) nextFieldErrors.start_date = "Choose a start date.";
    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    setIsSubmitting(true);
    try {
      if (isEditing) {
        await onSubmit({
          name,
          account_id: accountId,
          category_id: categoryId === NO_CATEGORY ? undefined : categoryId,
          clear_category: categoryId === NO_CATEGORY,
          type,
          amount_minor: amountMinor as number,
          frequency,
        });
      } else {
        await onSubmit({
          name,
          account_id: accountId,
          category_id: categoryId === NO_CATEGORY ? null : categoryId,
          type,
          amount_minor: amountMinor as number,
          frequency,
          start_date: startDate,
        });
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
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="recurring-name">Name</Label>
        <Input
          id="recurring-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Netflix"
        />
        <FormError message={fieldErrors.name ?? null} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="recurring-type">Type</Label>
        <Select
          id="recurring-type"
          value={type}
          onChange={(e) => setType(e.target.value as "income" | "expense")}
        >
          <option value="expense">Expense</option>
          <option value="income">Income</option>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="recurring-account">Account</Label>
        <Select
          id="recurring-account"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
        >
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
        <FormError message={fieldErrors.account_id ?? null} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="recurring-category">Category (optional)</Label>
        <Select
          id="recurring-category"
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
        >
          <option value={NO_CATEGORY}>No category</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.icon} {category.name}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="recurring-amount">Amount ({currency})</Label>
        <Input
          id="recurring-amount"
          inputMode="decimal"
          value={amountInput}
          onChange={(e) => setAmountInput(e.target.value)}
        />
        <FormError message={fieldErrors.amount ?? null} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="recurring-frequency">Frequency</Label>
        <Select
          id="recurring-frequency"
          value={frequency}
          onChange={(e) => setFrequency(e.target.value as typeof frequency)}
        >
          {RECURRENCE_FREQUENCIES.map((freq) => (
            <option key={freq} value={freq}>
              {FREQUENCY_LABELS[freq]}
            </option>
          ))}
        </Select>
      </div>

      {isEditing ? (
        <div className="flex flex-col gap-1.5">
          <Label>Start date</Label>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {recurring.start_date} (can&apos;t be changed)
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="recurring-start-date">Start date</Label>
          <Input
            id="recurring-start-date"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <FormError message={fieldErrors.start_date ?? null} />
        </div>
      )}

      <FormError message={error} />

      <div className="mt-2 flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isSubmitting}>
          {isEditing ? "Save changes" : "Add recurring transaction"}
        </Button>
      </div>
    </form>
  );
}
