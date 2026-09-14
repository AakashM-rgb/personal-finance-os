"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import type { Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import type { Category } from "@/lib/categories";
import { minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";
import { createTransaction, parseQuickAdd, type QuickAddParseResult } from "@/lib/transactions";
import { useAuth } from "@/lib/auth-context";

interface QuickAddBarProps {
  accounts: Account[];
  categories: Category[];
  onCreated: () => void;
}

const DEBOUNCE_MS = 400;

export function QuickAddBar({ accounts, categories, onCreated }: QuickAddBarProps) {
  const { accessToken } = useAuth();
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<QuickAddParseResult | null>(null);
  const [isParsing, setIsParsing] = useState(false);

  const [editedAmount, setEditedAmount] = useState("");
  const [editedCategoryId, setEditedCategoryId] = useState("");
  const [editedDescription, setEditedDescription] = useState("");
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? "");

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleTextChange(value: string) {
    setText(value);
    if (value.trim() === "") {
      setParsed(null);
      setEditedAmount("");
      setEditedCategoryId("");
      setEditedDescription("");
    }
  }

  useEffect(() => {
    if (!accessToken || text.trim().length === 0) return;
    let isActive = true;

    const timeoutId = setTimeout(() => {
      setIsParsing(true);
      void parseQuickAdd(accessToken, text)
        .then((result) => {
          if (!isActive) return;
          setParsed(result);
          setEditedAmount(
            result.amount_minor != null ? minorUnitsToInputValue(result.amount_minor) : ""
          );
          setEditedCategoryId(result.category_id ?? "");
          setEditedDescription(result.description ?? "");
        })
        .catch(() => {
          if (isActive) setParsed(null);
        })
        .finally(() => {
          if (isActive) setIsParsing(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      isActive = false;
      clearTimeout(timeoutId);
    };
  }, [text, accessToken]);

  async function handleAdd() {
    if (!accessToken || !accountId) return;
    const amountMinor = parseMoneyToMinorUnits(editedAmount);
    if (amountMinor === null || amountMinor <= 0) {
      setError("Enter a valid amount.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      await createTransaction(accessToken, {
        account_id: accountId,
        type: "expense",
        amount_minor: amountMinor,
        category_id: editedCategoryId || null,
        description: editedDescription || null,
      });
      setText("");
      setParsed(null);
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add that transaction.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const hasValidAmount = parsed?.amount_minor != null;
  const isLowConfidence = parsed !== null && parsed.confidence === "low" && hasValidAmount;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <label htmlFor="quick-add-input" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
        Quick add
      </label>
      <div className="mt-1.5 flex gap-2">
        <input
          id="quick-add-input"
          placeholder='Try "120 food lunch" or "450 uber college"'
          value={text}
          onChange={(e) => handleTextChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && hasValidAmount) {
              e.preventDefault();
              void handleAdd();
            }
          }}
          className="h-10 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
      </div>

      {text.trim() !== "" && (
        <div className="mt-3 flex flex-col gap-3 rounded-md border border-zinc-100 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
          {isParsing && <p className="text-xs text-zinc-500">Reading that…</p>}

          {!isParsing && parsed && !hasValidAmount && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {parsed.error ?? "Couldn't understand that. Try \"120 food lunch\"."}
            </p>
          )}

          {!isParsing && hasValidAmount && (
            <>
              {isLowConfidence && (
                <p className="text-xs font-medium text-amber-600 dark:text-amber-400">
                  {parsed.error ?? "Not sure about the category - please check before adding."}
                </p>
              )}
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-zinc-500">Amount</span>
                  <input
                    value={editedAmount}
                    onChange={(e) => setEditedAmount(e.target.value)}
                    inputMode="decimal"
                    className="h-9 w-28 rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-zinc-500">Category</span>
                  <Select
                    value={editedCategoryId}
                    onChange={(e) => setEditedCategoryId(e.target.value)}
                    className="h-9 w-44"
                  >
                    <option value="">No category</option>
                    {categories.map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.icon} {category.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-1 flex-col gap-1">
                  <span className="text-xs text-zinc-500">Description</span>
                  <input
                    value={editedDescription}
                    onChange={(e) => setEditedDescription(e.target.value)}
                    className="h-9 w-full rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-zinc-500">Account</span>
                  <Select
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                    className="h-9 w-36"
                  >
                    {accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <Button isLoading={isSubmitting} onClick={() => void handleAdd()}>
                  Add
                </Button>
              </div>
            </>
          )}

          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
      )}
    </div>
  );
}
