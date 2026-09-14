"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import type { Category, CategoryCreateInput, CategoryUpdateInput } from "@/lib/categories";
import { minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";

interface CategoryFormProps {
  category?: Category;
  parentOptions: Category[];
  onSubmit: (input: CategoryCreateInput | CategoryUpdateInput) => Promise<void>;
  onCancel: () => void;
}

export function CategoryForm({ category, parentOptions, onSubmit, onCancel }: CategoryFormProps) {
  const isEditing = category !== undefined;
  const [name, setName] = useState(category?.name ?? "");
  const [icon, setIcon] = useState(category?.icon ?? "🏷️");
  const [color, setColor] = useState(category?.color ?? "#3B82F6");
  const [budgetInput, setBudgetInput] = useState(
    category?.budget_minor != null ? minorUnitsToInputValue(category.budget_minor) : ""
  );
  const [parentId, setParentId] = useState(category?.parent_id ?? "");

  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    let budgetMinor: number | null = null;
    if (budgetInput.trim() !== "") {
      budgetMinor = parseMoneyToMinorUnits(budgetInput);
      if (budgetMinor === null) {
        setFieldErrors({ budget: "Enter a valid amount." });
        return;
      }
    }

    setIsSubmitting(true);
    try {
      await onSubmit({
        name,
        icon,
        color,
        budget_minor: budgetMinor,
        parent_id: parentId || null,
        ...(isEditing ? { clear_parent: parentId === "" } : {}),
      });
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
        <Label htmlFor="category-name">Name</Label>
        <Input id="category-name" required value={name} onChange={(e) => setName(e.target.value)} />
        <FormError message={fieldErrors.name ?? null} />
      </div>

      <div className="grid grid-cols-[1fr_auto] gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="category-icon">Icon (emoji)</Label>
          <Input id="category-icon" value={icon} onChange={(e) => setIcon(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="category-color">Color</Label>
          <input
            id="category-color"
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            className="h-10 w-14 rounded-md border border-zinc-300 dark:border-zinc-700"
          />
        </div>
      </div>
      <FormError message={fieldErrors.color ?? null} />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="category-budget">Suggested monthly budget (optional)</Label>
        <Input
          id="category-budget"
          inputMode="decimal"
          value={budgetInput}
          onChange={(e) => setBudgetInput(e.target.value)}
        />
        <FormError message={fieldErrors.budget ?? null} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="category-parent">Parent category (optional)</Label>
        <Select
          id="category-parent"
          value={parentId}
          onChange={(e) => setParentId(e.target.value)}
        >
          <option value="">None - top-level category</option>
          {parentOptions.map((option) => (
            <option key={option.id} value={option.id}>
              {option.icon} {option.name}
            </option>
          ))}
        </Select>
        <FormError message={fieldErrors.parent_id ?? null} />
      </div>

      <FormError message={error} />

      <div className="mt-2 flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isSubmitting}>
          {isEditing ? "Save changes" : "Add category"}
        </Button>
      </div>
    </form>
  );
}
