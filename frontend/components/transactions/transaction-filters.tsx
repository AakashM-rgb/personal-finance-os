"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
import { endOfLocalDayIso, startOfLocalDayIso, toLocalDateInputValue } from "@/lib/dates";
import { minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";
import type { TransactionFilters as Filters } from "@/lib/transactions";

interface TransactionFiltersProps {
  accounts: Account[];
  categories: Category[];
  filters: Filters;
  onChange: (filters: Filters) => void;
}

export function TransactionFiltersBar({
  accounts,
  categories,
  filters,
  onChange,
}: TransactionFiltersProps) {
  // Remounts the amount inputs on "Clear filters", so even text that was
  // never applied (invalid input) is cleared too.
  const [resetKey, setResetKey] = useState(0);

  function update(patch: Partial<Filters>) {
    onChange({ ...filters, ...patch, offset: 0 });
  }

  // Amounts are compared in minor units; parse them in the filtered account's
  // currency when one is chosen (v1 has one base currency per user otherwise).
  const currency =
    accounts.find((a) => a.id === filters.account_id)?.currency ?? accounts[0]?.currency ?? "INR";
  const hasActiveFilters = Boolean(
    filters.q ||
      filters.type ||
      filters.category_id ||
      filters.account_id ||
      filters.date_from ||
      filters.date_to ||
      filters.amount_min != null ||
      filters.amount_max != null ||
      filters.is_recurring ||
      (filters.tags && filters.tags.length > 0)
  );
  const rangeError =
    filters.amount_min != null && filters.amount_max != null && filters.amount_min > filters.amount_max
      ? "Min amount is greater than max amount - no transactions can match."
      : null;

  function clearFilters() {
    setResetKey((n) => n + 1);
    onChange({
      sort_by: filters.sort_by,
      sort_dir: filters.sort_dir,
      limit: filters.limit,
      offset: 0,
    });
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <Input
        placeholder="Search description, merchant, notes…"
        value={filters.q ?? ""}
        onChange={(e) => update({ q: e.target.value || undefined })}
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Select
          value={filters.type ?? ""}
          onChange={(e) => update({ type: (e.target.value || undefined) as Filters["type"] })}
        >
          <option value="">All types</option>
          <option value="income">Income</option>
          <option value="expense">Expense</option>
          <option value="transfer">Transfer</option>
        </Select>

        <Select
          value={filters.category_id ?? ""}
          onChange={(e) => update({ category_id: e.target.value || undefined })}
        >
          <option value="">All categories</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.icon} {category.name}
            </option>
          ))}
        </Select>

        <Select
          value={filters.account_id ?? ""}
          onChange={(e) => update({ account_id: e.target.value || undefined })}
        >
          <option value="">All accounts</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>

        <Input
          type="date"
          aria-label="From date"
          value={filters.date_from ? toLocalDateInputValue(new Date(filters.date_from)) : ""}
          onChange={(e) =>
            update({ date_from: e.target.value ? startOfLocalDayIso(e.target.value) : undefined })
          }
        />
        <Input
          type="date"
          aria-label="To date"
          value={filters.date_to ? toLocalDateInputValue(new Date(filters.date_to)) : ""}
          onChange={(e) =>
            update({ date_to: e.target.value ? endOfLocalDayIso(e.target.value) : undefined })
          }
        />

        <Select
          value={`${filters.sort_by ?? "occurred_at"}:${filters.sort_dir ?? "desc"}`}
          onChange={(e) => {
            const [sortBy, sortDir] = e.target.value.split(":") as [Filters["sort_by"], Filters["sort_dir"]];
            update({ sort_by: sortBy, sort_dir: sortDir });
          }}
        >
          <option value="occurred_at:desc">Newest first</option>
          <option value="occurred_at:asc">Oldest first</option>
          <option value="amount_minor:desc">Amount: high to low</option>
          <option value="amount_minor:asc">Amount: low to high</option>
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <AmountFilterInput
          key={`min-${resetKey}`}
          label="Min amount"
          valueMinor={filters.amount_min}
          currency={currency}
          onChange={(amountMinor) => update({ amount_min: amountMinor })}
        />
        <AmountFilterInput
          key={`max-${resetKey}`}
          label="Max amount"
          valueMinor={filters.amount_max}
          currency={currency}
          onChange={(amountMinor) => update({ amount_max: amountMinor })}
        />
        <Input
          placeholder="Tags (comma-separated)"
          value={(filters.tags ?? []).join(", ")}
          onChange={(e) =>
            update({
              tags: e.target.value
                ? e.target.value.split(",").map((t) => t.trim()).filter(Boolean)
                : undefined,
            })
          }
        />
        <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
          <input
            type="checkbox"
            checked={filters.is_recurring ?? false}
            onChange={(e) => update({ is_recurring: e.target.checked || undefined })}
          />
          Recurring only
        </label>
      </div>

      <FormError message={rangeError} />

      {hasActiveFilters && (
        <Button type="button" variant="ghost" className="self-start" onClick={clearFilters}>
          Clear filters
        </Button>
      )}
    </div>
  );
}

interface AmountFilterInputProps {
  label: string;
  valueMinor: number | undefined;
  currency: string;
  onChange: (amountMinor: number | undefined) => void;
}

/** Keeps the user's own text and only applies a filter once it's a valid
 * amount - parsed by the shared lib/money.ts, never with floating-point math.
 * Invalid text clears this bound rather than filtering on a guess. */
function AmountFilterInput({ label, valueMinor, currency, onChange }: AmountFilterInputProps) {
  const [text, setText] = useState(() =>
    valueMinor != null ? minorUnitsToInputValue(valueMinor, currency) : ""
  );
  const [isInvalid, setIsInvalid] = useState(false);
  // The value this input itself last applied - anything else arriving via
  // props is an external change (e.g. "Clear filters") to resync the text to.
  const lastEmittedRef = useRef(valueMinor);

  useEffect(() => {
    if (valueMinor === lastEmittedRef.current) return;
    lastEmittedRef.current = valueMinor;
    setText(valueMinor != null ? minorUnitsToInputValue(valueMinor, currency) : "");
    setIsInvalid(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resync on applied-value changes only
  }, [valueMinor]);

  function emit(amountMinor: number | undefined) {
    if (amountMinor === valueMinor) return;
    lastEmittedRef.current = amountMinor;
    onChange(amountMinor);
  }

  function handleChange(nextText: string) {
    setText(nextText);
    // A trailing "." is an amount still being typed ("12." on the way to "12.50").
    const trimmed = nextText.trim().replace(/\.$/, "");
    if (trimmed === "") {
      setIsInvalid(false);
      emit(undefined);
      return;
    }
    const amountMinor = parseMoneyToMinorUnits(trimmed, currency);
    if (amountMinor === null || amountMinor < 0) {
      setIsInvalid(true);
      emit(undefined);
      return;
    }
    setIsInvalid(false);
    emit(amountMinor);
  }

  return (
    <div className="flex flex-col gap-1">
      <Input
        placeholder={label}
        aria-label={label}
        aria-invalid={isInvalid || undefined}
        inputMode="decimal"
        value={text}
        onChange={(e) => handleChange(e.target.value)}
      />
      {isInvalid && <FormError message="Enter an amount like 250 or 99.50." />}
    </div>
  );
}
