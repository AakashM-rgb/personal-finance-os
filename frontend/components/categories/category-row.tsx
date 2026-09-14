"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";

interface CategoryRowProps {
  category: Category;
  isChild: boolean;
  onEdit: () => void;
  onDelete: () => Promise<void>;
}

export function CategoryRow({ category, isChild, onEdit, onDelete }: CategoryRowProps) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleConfirmDelete() {
    setIsDeleting(true);
    try {
      await onDelete();
    } finally {
      setIsDeleting(false);
      setIsConfirmingDelete(false);
    }
  }

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
        <span className="text-xs text-zinc-400 dark:text-zinc-500">Default</span>
      ) : isConfirmingDelete ? (
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setIsConfirmingDelete(false)}>
            Cancel
          </Button>
          <Button
            className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
            isLoading={isDeleting}
            onClick={() => void handleConfirmDelete()}
          >
            Confirm
          </Button>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onEdit}>
            Edit
          </Button>
          <Button variant="ghost" onClick={() => setIsConfirmingDelete(true)}>
            Delete
          </Button>
        </div>
      )}
    </div>
  );
}
