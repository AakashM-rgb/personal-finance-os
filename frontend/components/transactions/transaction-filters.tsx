"use client";

import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
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
  function update(patch: Partial<Filters>) {
    onChange({ ...filters, ...patch, offset: 0 });
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
          value={filters.date_from?.slice(0, 10) ?? ""}
          onChange={(e) => update({ date_from: e.target.value ? `${e.target.value}T00:00:00Z` : undefined })}
        />
        <Input
          type="date"
          aria-label="To date"
          value={filters.date_to?.slice(0, 10) ?? ""}
          onChange={(e) => update({ date_to: e.target.value ? `${e.target.value}T23:59:59Z` : undefined })}
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
        <Input
          placeholder="Min amount"
          inputMode="decimal"
          value={filters.amount_min != null ? String(filters.amount_min / 100) : ""}
          onChange={(e) =>
            update({ amount_min: e.target.value ? Math.round(Number(e.target.value) * 100) : undefined })
          }
        />
        <Input
          placeholder="Max amount"
          inputMode="decimal"
          value={filters.amount_max != null ? String(filters.amount_max / 100) : ""}
          onChange={(e) =>
            update({ amount_max: e.target.value ? Math.round(Number(e.target.value) * 100) : undefined })
          }
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
    </div>
  );
}
