"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";
import type { SavingsGoal, SavingsGoalCreateInput, SavingsGoalUpdateInput } from "@/lib/goals";
import { minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";

interface GoalFormProps {
  goal?: SavingsGoal;
  onSubmit: (input: SavingsGoalCreateInput | SavingsGoalUpdateInput) => Promise<void>;
  onCancel: () => void;
}

const DEFAULT_CURRENCY = "INR";

export function GoalForm({ goal, onSubmit, onCancel }: GoalFormProps) {
  const isEditing = goal !== undefined;
  const currency = goal?.currency ?? DEFAULT_CURRENCY;

  const [name, setName] = useState(goal?.name ?? "");
  const [targetInput, setTargetInput] = useState(
    goal ? minorUnitsToInputValue(goal.target_amount_minor, currency) : ""
  );
  const [currentInput, setCurrentInput] = useState(
    goal ? minorUnitsToInputValue(goal.current_amount_minor, currency) : "0"
  );
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    const targetAmountMinor = parseMoneyToMinorUnits(targetInput, currency);
    const currentAmountMinor = parseMoneyToMinorUnits(currentInput, currency);
    const nextFieldErrors: Record<string, string> = {};

    if (!name.trim()) {
      nextFieldErrors.name = "Enter a name for this goal.";
    }
    if (targetAmountMinor === null || targetAmountMinor <= 0) {
      nextFieldErrors.target_amount_minor = "Enter a target amount greater than zero.";
    }
    if (currentAmountMinor === null || currentAmountMinor < 0) {
      nextFieldErrors.current_amount_minor = "Enter a valid saved-so-far amount.";
    }
    if (
      targetAmountMinor !== null &&
      currentAmountMinor !== null &&
      currentAmountMinor > targetAmountMinor
    ) {
      nextFieldErrors.current_amount_minor = "Cannot exceed the target amount.";
    }
    if (!targetDate) {
      nextFieldErrors.target_date = "Choose a target date.";
    }
    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    setIsSubmitting(true);
    try {
      if (isEditing) {
        await onSubmit({
          name,
          target_amount_minor: targetAmountMinor as number,
          current_amount_minor: currentAmountMinor as number,
          target_date: targetDate,
        });
      } else {
        await onSubmit({
          name,
          target_amount_minor: targetAmountMinor as number,
          current_amount_minor: currentAmountMinor as number,
          currency,
          target_date: targetDate,
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
        <Label htmlFor="goal-name">Goal name</Label>
        <Input
          id="goal-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New Laptop"
        />
        <FormError message={fieldErrors.name ?? null} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="goal-target">Target amount ({currency})</Label>
        <Input
          id="goal-target"
          inputMode="decimal"
          value={targetInput}
          onChange={(e) => setTargetInput(e.target.value)}
        />
        <FormError message={fieldErrors.target_amount_minor ?? null} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="goal-current">Current amount saved ({currency})</Label>
        <Input
          id="goal-current"
          inputMode="decimal"
          value={currentInput}
          onChange={(e) => setCurrentInput(e.target.value)}
        />
        <FormError message={fieldErrors.current_amount_minor ?? null} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="goal-date">Target date</Label>
        <Input
          id="goal-date"
          type="date"
          value={targetDate}
          onChange={(e) => setTargetDate(e.target.value)}
        />
        <FormError message={fieldErrors.target_date ?? null} />
      </div>

      <FormError message={error} />

      <div className="mt-2 flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isSubmitting}>
          {isEditing ? "Save changes" : "Add goal"}
        </Button>
      </div>
    </form>
  );
}
