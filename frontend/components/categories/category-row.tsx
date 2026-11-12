"use client";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import { useConfirmableAction } from "@/lib/use-confirmable-action";

interface CategoryRowProps {
  category: Category;
  isChild: boolean;
  onEdit: () => void;
  onDelete: () => Promise<void>;
}

export function CategoryRow({ category, isChild, onEdit, onDelete }: CategoryRowProps) {
  const confirmAction = useConfirmableAction(
    onDelete,
    "Couldn't delete this category. Please try again."
  );

  return (
    <div
      className={`flex items-center justify-between gap-3 border-b border-zinc-100 py-3 last:border-0 dark:border-zinc-800 ${
        isChild ? "pl-8" : ""
      }`}
    >
      <div className="flex items-center gap-3">
        <span
          className="flex h-8 w-8 items-center justify-center rounded-full text-base"
          style={{ backgroundColor: `${category.color}22` }}
          aria-hidden="true"
        >
          {category.icon}
        </span>
        <div>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">{category.name}</p>
          {category.budget_minor != null && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Suggested budget: {formatMoney(category.budget_minor)}/mo
            </p>
          )}
        </div>
      </div>

      {category.is_system ? (
        // zinc-400 on white is 2.62:1, well under WCAG AA's 4.5:1 for
        // normal-size text (verified with axe-core) - zinc-600 clears it.
        <span className="text-xs text-zinc-600 dark:text-zinc-500">Default</span>
      ) : confirmAction.isConfirming ? (
        <div className="flex flex-col items-end gap-1">
          <div className="flex gap-2">
            <Button variant="secondary" onClick={confirmAction.cancel}>
              Cancel
            </Button>
            <Button
              className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
              isLoading={confirmAction.isPending}
              onClick={() => void confirmAction.confirm()}
            >
              Confirm
            </Button>
          </div>
          <FormError message={confirmAction.error} />
        </div>
      ) : (
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onEdit}>
            Edit
          </Button>
          <Button variant="ghost" onClick={confirmAction.start}>
            Delete
          </Button>
        </div>
      )}
    </div>
  );
}
