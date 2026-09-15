"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import type { Budget, BudgetCreateInput, BudgetSuggestion, BudgetUpdateInput } from "@/lib/budgets";
import type { Category } from "@/lib/categories";
import { minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";

interface BudgetFormProps {
  budget?: Budget;
  availableCategories: Category[];
  suggestions?: BudgetSuggestion[];
  currency: string;
  onSubmit: (input: BudgetCreateInput | BudgetUpdateInput) => Promise<void>;
  onCancel: () => void;
}

export function BudgetForm({
  budget,
  availableCategories,
  suggestions = [],
  currency,
  onSubmit,
  onCancel,
}: BudgetFormProps) {
  const isEditing = budget !== undefined;

  const [categoryId, setCategoryId] = useState(
    budget?.category_id ?? availableCategories[0]?.id ?? ""
  );
  const [amountInput, setAmountInput] = useState(
    budget ? minorUnitsToInputValue(budget.amount_minor, currency) : ""
  );
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    const amountMinor = parseMoneyToMinorUnits(amountInput, currency);
    if (amountMinor === null || amountMinor <= 0) {
      setFieldErrors({ amount: "Enter an amount greater than zero." });
      return;
    }

    setIsSubmitting(true);
    try {
      if (isEditing) {
        await onSubmit({ amount_minor: amountMinor });
      } else {
        await onSubmit({ category_id: categoryId, amount_minor: amountMinor });
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

  const activeSuggestion = suggestions.find((s) => s.category_id === categoryId);

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {isEditing ? (
        <div className="flex flex-col gap-1.5">
          <Label>Category</Label>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {budget.category_icon} {budget.category_name} (can&apos;t be changed)
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="budget-category">Category</Label>
          <Select
            id="budget-category"
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
          >
            {availableCategories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.icon} {category.name}
              </option>
            ))}
          </Select>
          <FormError message={fieldErrors.category_id ?? null} />
        </div>
      )}

      {!isEditing && activeSuggestion && (
        <button
          type="button"
          onClick={() =>
            setAmountInput(minorUnitsToInputValue(activeSuggestion.suggested_amount_minor, currency))
          }
          className="rounded-md border border-dashed border-zinc-300 p-2 text-left text-xs text-zinc-600 hover:border-zinc-400 dark:border-zinc-700 dark:text-zinc-400"
        >
          Suggested: {minorUnitsToInputValue(activeSuggestion.suggested_amount_minor, currency)}{" "}
          {currency} ({activeSuggestion.based_on}) - tap to use
        </button>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="budget-amount">Monthly limit ({currency})</Label>
        <Input
          id="budget-amount"
          inputMode="decimal"
          required
          value={amountInput}
          onChange={(e) => setAmountInput(e.target.value)}
        />
        <FormError message={fieldErrors.amount ?? null} />
      </div>

      <FormError message={error} />

      <div className="mt-2 flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isSubmitting}>
          {isEditing ? "Save changes" : "Add budget"}
        </Button>
      </div>
    </form>
  );
}
