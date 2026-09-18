"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { MerchantRule } from "@/lib/merchant-rules";

interface MerchantRuleRowProps {
  rule: MerchantRule;
  onDelete: () => Promise<void>;
}

export function MerchantRuleRow({ rule, onDelete }: MerchantRuleRowProps) {
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
    <div className="flex items-center justify-between gap-3 border-b border-zinc-100 py-3 last:border-0 dark:border-zinc-800">
      <div className="flex items-center gap-3">
        <span
          className="flex h-8 w-8 items-center justify-center rounded-full text-base"
          style={{ backgroundColor: `${rule.category_color}22` }}
          aria-hidden="true"
        >
          {rule.category_icon}
        </span>
        <div>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">{rule.merchant_key}</p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">→ {rule.category_name}</p>
        </div>
      </div>

      {isConfirmingDelete ? (
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
        <Button variant="ghost" onClick={() => setIsConfirmingDelete(true)}>
          Remove
        </Button>
      )}
    </div>
  );
}
