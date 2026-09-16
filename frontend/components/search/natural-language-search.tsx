"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { formatMoney } from "@/lib/money";
import {
  SEARCH_EXAMPLES,
  SEARCH_MAX_QUERY_LENGTH,
  searchFinancial,
  type SearchResponse,
} from "@/lib/search";

const TYPE_COLOR: Record<string, string> = {
  income: "text-emerald-600 dark:text-emerald-400",
  expense: "text-red-600 dark:text-red-400",
  transfer: "text-zinc-600 dark:text-zinc-400",
};

const TYPE_SIGN: Record<string, string> = { income: "+", expense: "-", transfer: "" };

/** Renders the plain-language chips describing exactly what will run (or
 * did run) - the interpreted criteria is always shown, never a hidden
 * black box, per CLAUDE.md's ambiguity/confirmation requirement. */
function CriteriaChips({ interpretation }: { interpretation: SearchResponse["interpretation"] }) {
  const chips: string[] = [];
  if (interpretation.search_text) chips.push(`"${interpretation.search_text}"`);
  if (interpretation.category_name) chips.push(interpretation.category_name);
  if (interpretation.transaction_type) chips.push(interpretation.transaction_type);
  if (interpretation.start_date && interpretation.end_date) {
    chips.push(
      interpretation.start_date === interpretation.end_date
        ? interpretation.start_date
        : `${interpretation.start_date} → ${interpretation.end_date}`
    );
  }
  if (interpretation.min_amount_minor != null) {
    chips.push(`above ${formatMoney(interpretation.min_amount_minor, interpretation.currency)}`);
  }
  if (interpretation.max_amount_minor != null) {
    chips.push(`below ${formatMoney(interpretation.max_amount_minor, interpretation.currency)}`);
  }
  if (interpretation.is_weekend_only) chips.push("weekends only");
  if (interpretation.subscriptions_only) chips.push("subscriptions only");
  if (interpretation.sort === "amount_desc") chips.push("biggest first");
  if (interpretation.sort === "amount_asc") chips.push("smallest first");

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2" aria-label="Interpreted search criteria">
      {chips.map((chip) => (
        <span
          key={chip}
          className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
        >
          {chip}
        </span>
      ))}
    </div>
  );
}

interface NaturalLanguageSearchProps {
  /** Notified whenever an executed (non-ambiguous) search has results, so a
   * parent page can hide its normal filtered list while one is active. */
  onActiveChange?: (active: boolean) => void;
}

export function NaturalLanguageSearch({ onActiveChange }: NaturalLanguageSearchProps) {
  const { accessToken } = useAuth();
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);

  function setActive(active: boolean) {
    onActiveChange?.(active);
  }

  async function runSearch(searchQuery: string, options: { confirmed?: boolean; categoryOverrideId?: string } = {}) {
    if (!accessToken || !searchQuery.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await searchFinancial(accessToken, searchQuery, options);
      setResponse(result);
      setActive(!result.requires_confirmation);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't run that search. Please try again.");
      setResponse(null);
      setActive(false);
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    void runSearch(query);
  }

  function handleClear() {
    setQuery("");
    setResponse(null);
    setError(null);
    setActive(false);
  }

  return (
    <Card className="flex flex-col gap-4">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="nl-search-input" className="sr-only">
          Search your finances in plain language
        </label>
        <Input
          id="nl-search-input"
          placeholder='Try "food last month" or "Amazon purchases above ₹1000"'
          value={query}
          maxLength={SEARCH_MAX_QUERY_LENGTH}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1"
        />
        <div className="flex gap-2">
          <Button type="submit" isLoading={isLoading} disabled={!query.trim()}>
            Search
          </Button>
          {(response || error) && (
            <Button type="button" variant="secondary" onClick={handleClear}>
              Clear
            </Button>
          )}
        </div>
      </form>

      {!response && !error && !isLoading && (
        <div className="flex flex-wrap gap-2">
          {SEARCH_EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuery(example);
                void runSearch(example);
              }}
              className="rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900"
            >
              {example}
            </button>
          ))}
        </div>
      )}

      {isLoading && (
        <div className="flex flex-col gap-2" role="status">
          <span className="sr-only">Searching…</span>
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400"
        >
          {error}
        </div>
      )}

      {response && !isLoading && (
        <div className="flex flex-col gap-4">
          <CriteriaChips interpretation={response.interpretation} />

          {response.requires_confirmation && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
              <p>{response.ambiguity_reason}</p>

              {response.ambiguous_categories.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {response.ambiguous_categories.map((category) => (
                    <Button
                      key={category.id}
                      type="button"
                      variant="secondary"
                      onClick={() => void runSearch(query, { categoryOverrideId: category.id })}
                    >
                      {category.icon} {category.name}
                    </Button>
                  ))}
                  <Button type="button" variant="ghost" onClick={() => void runSearch(query, { confirmed: true })}>
                    Search without a category
                  </Button>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  className="mt-3"
                  onClick={() => void runSearch(query, { confirmed: true })}
                >
                  Search anyway
                </Button>
              )}
            </div>
          )}

          {!response.requires_confirmation && response.results.length === 0 && (
            <div className="rounded-xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
              No transactions matched that search.
            </div>
          )}

          {!response.requires_confirmation && response.results.length > 0 && (
            <div className="flex flex-col">
              {response.results.map((result) => {
                const date = new Date(result.occurred_at);
                return (
                  <div
                    key={result.id}
                    className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-100 py-3 last:border-0 dark:border-zinc-800"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
                        {result.description || result.merchant || result.category_name}
                      </p>
                      <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                        {date.toLocaleDateString(undefined, {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                        {" · "}
                        {result.category_name}
                      </p>
                    </div>
                    <p className={`text-sm font-semibold ${TYPE_COLOR[result.type]}`}>
                      {TYPE_SIGN[result.type]}
                      {formatMoney(result.amount_minor, result.currency)}
                    </p>
                  </div>
                );
              })}

              <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                Showing {response.result_count} of {response.total_matching}
                {response.limited ? " (narrow your search to see more)" : ""}
              </p>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
