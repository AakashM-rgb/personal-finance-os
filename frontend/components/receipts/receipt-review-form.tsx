"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import type { Category } from "@/lib/categories";
import { minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";
import type { Receipt, ReceiptConfirmInput, ReceiptItem } from "@/lib/receipts";

const NO_CATEGORY = "__none__";

interface EditableItem {
  description: string;
  quantity: string;
  lineTotalInput: string;
}

function itemsFromReceipt(receipt: Receipt): EditableItem[] {
  const source = receipt.confirmed_items.length > 0 ? receipt.confirmed_items : receipt.extraction?.items ?? [];
  return source.map((item: ReceiptItem) => ({
    description: item.description,
    quantity: item.quantity ?? "",
    lineTotalInput:
      item.line_total_minor !== null ? minorUnitsToInputValue(item.line_total_minor) : "",
  }));
}

interface ReceiptReviewFormProps {
  receipt: Receipt;
  categories: Category[];
  onSubmit: (input: ReceiptConfirmInput) => Promise<void>;
}

export function ReceiptReviewForm({ receipt, categories, onSubmit }: ReceiptReviewFormProps) {
  const extraction = receipt.extraction;

  const [merchant, setMerchant] = useState(receipt.confirmed_merchant ?? extraction?.merchant ?? "");
  const [date, setDate] = useState(receipt.confirmed_date ?? extraction?.date ?? "");
  const [totalInput, setTotalInput] = useState(
    minorUnitsToInputValue(receipt.confirmed_total_minor ?? extraction?.total_minor ?? 0)
  );
  const [taxInput, setTaxInput] = useState(
    receipt.confirmed_tax_minor !== null || extraction?.tax_minor !== null
      ? minorUnitsToInputValue(receipt.confirmed_tax_minor ?? extraction?.tax_minor ?? 0)
      : ""
  );
  const [categoryId, setCategoryId] = useState(
    receipt.category_id ?? extraction?.suggested_category_id ?? NO_CATEGORY
  );
  const [items, setItems] = useState<EditableItem[]>(() => itemsFromReceipt(receipt));

  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  function updateItem(index: number, patch: Partial<EditableItem>) {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  function removeItem(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }

  function addItem() {
    setItems((prev) => [...prev, { description: "", quantity: "", lineTotalInput: "" }]);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    const totalMinor = totalInput.trim() ? parseMoneyToMinorUnits(totalInput) : null;
    const taxMinor = taxInput.trim() ? parseMoneyToMinorUnits(taxInput) : null;

    const nextFieldErrors: Record<string, string> = {};
    if (totalInput.trim() && totalMinor === null) {
      nextFieldErrors.total_minor = "Enter a valid amount.";
    }
    if (taxInput.trim() && taxMinor === null) {
      nextFieldErrors.tax_minor = "Enter a valid amount.";
    }
    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    const cleanedItems = items
      .filter((item) => item.description.trim())
      .map((item) => ({
        description: item.description.trim(),
        quantity: item.quantity.trim() || null,
        unit_price_minor: null,
        line_total_minor: item.lineTotalInput.trim()
          ? parseMoneyToMinorUnits(item.lineTotalInput)
          : null,
      }));

    const input: ReceiptConfirmInput = {
      merchant: merchant.trim() || null,
      date: date || null,
      total_minor: totalMinor,
      tax_minor: taxMinor,
      items: cleanedItems,
      category_id: categoryId === NO_CATEGORY ? null : categoryId,
    };

    setIsSubmitting(true);
    try {
      await onSubmit(input);
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
      {extraction && extraction.confidence !== null && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {extraction.error
            ? `OCR couldn't read this file: ${extraction.error}`
            : `Extracted by ${extraction.provider} (confidence ${Math.round(extraction.confidence * 100)}%). Review and correct anything below before saving.`}
        </p>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="receipt-merchant">Merchant</Label>
        <Input
          id="receipt-merchant"
          value={merchant}
          onChange={(e) => setMerchant(e.target.value)}
          placeholder="e.g. Corner Cafe"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="receipt-date">Date</Label>
          <Input id="receipt-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="receipt-category">Category</Label>
          <Select id="receipt-category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value={NO_CATEGORY}>No category</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.icon} {category.name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="receipt-total">Total</Label>
          <Input
            id="receipt-total"
            inputMode="decimal"
            value={totalInput}
            onChange={(e) => setTotalInput(e.target.value)}
          />
          <FormError message={fieldErrors.total_minor ?? null} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="receipt-tax">Tax (optional)</Label>
          <Input
            id="receipt-tax"
            inputMode="decimal"
            value={taxInput}
            onChange={(e) => setTaxInput(e.target.value)}
          />
          <FormError message={fieldErrors.tax_minor ?? null} />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <Label>Items (optional)</Label>
          <button
            type="button"
            onClick={addItem}
            className="text-xs font-medium text-zinc-600 underline hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
          >
            + Add item
          </button>
        </div>
        {items.map((item, index) => (
          <div key={index} className="grid grid-cols-[1fr_4rem_5rem_auto] items-center gap-2">
            <Input
              aria-label="Item description"
              value={item.description}
              onChange={(e) => updateItem(index, { description: e.target.value })}
              placeholder="Description"
            />
            <Input
              aria-label="Item quantity"
              value={item.quantity}
              onChange={(e) => updateItem(index, { quantity: e.target.value })}
              placeholder="Qty"
            />
            <Input
              aria-label="Item amount"
              inputMode="decimal"
              value={item.lineTotalInput}
              onChange={(e) => updateItem(index, { lineTotalInput: e.target.value })}
              placeholder="Amount"
            />
            <button
              type="button"
              onClick={() => removeItem(index)}
              aria-label="Remove item"
              className="text-zinc-400 hover:text-red-600 dark:hover:text-red-400"
            >
              &times;
            </button>
          </div>
        ))}
      </div>

      <FormError message={error} />

      <div className="mt-2 flex justify-end">
        <Button type="submit" isLoading={isSubmitting}>
          {receipt.status === "confirmed" ? "Save corrections" : "Confirm details"}
        </Button>
      </div>
    </form>
  );
}
