"use client";

import { useEffect, useState } from "react";

import { CategoryBreakdown } from "@/components/dashboard/category-breakdown";
import { HealthScoreMeter } from "@/components/dashboard/health-score-meter";
import { MonthlySpendingCard } from "@/components/dashboard/monthly-spending-card";
import { RecentTransactionsList } from "@/components/dashboard/recent-transactions-list";
import { StatCard } from "@/components/dashboard/stat-card";
import { UpcomingPaymentsList } from "@/components/dashboard/upcoming-payments-list";
import { Skeleton } from "@/components/ui/skeleton";
import { listAccounts, type Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { listCategories, type Category } from "@/lib/categories";
import { getDashboard, type Dashboard } from "@/lib/dashboard";
import { formatMoney } from "@/lib/money";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const { accessToken, user } = useAuth();

  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void Promise.all([
      getDashboard(accessToken),
      listAccounts(accessToken),
      listCategories(accessToken),
    ])
      .then(([dashboardData, accountsData, categoriesData]) => {
        if (!isMounted) return;
        setDashboard(dashboardData);
        setAccounts(accountsData);
        setCategories(categoriesData);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof ApiError ? err.message : "Failed to load your dashboard.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  const isLoading = dashboard === null && !error;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          {greeting()}
          {user ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Here&apos;s what&apos;s happening with your money.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button type="button" onClick={reload} className="font-medium underline">
            Try again
          </button>
        </div>
      )}

      {isLoading && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-52" />
            <Skeleton className="h-52" />
          </div>
        </div>
      )}

      {!isLoading && dashboard !== null && accounts !== null && accounts.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Add your first account to start seeing your dashboard come to life.
          </p>
          <a href="/accounts" className="mt-2 inline-block text-sm font-medium underline">
            Add an account
          </a>
        </div>
      )}

      {!isLoading && dashboard !== null && accounts !== null && categories !== null && accounts.length > 0 && (
        <>
          {dashboard.excluded_other_currency_accounts > 0 && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {dashboard.excluded_other_currency_accounts} account
              {dashboard.excluded_other_currency_accounts > 1 ? "s" : ""} in a different currency
              {" "}aren&apos;t included in the totals below.
            </p>
          )}

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <StatCard
              label="Total balance"
              value={formatMoney(dashboard.total_balance_minor, dashboard.currency)}
            />
            <StatCard
              label="Net worth"
              value={formatMoney(dashboard.net_worth_minor, dashboard.currency)}
            />
            <StatCard
              label="Income"
              value={formatMoney(dashboard.total_income_minor, dashboard.currency)}
              sublabel="This month"
            />
            <StatCard
              label="Expenses"
              value={formatMoney(dashboard.total_expense_minor, dashboard.currency)}
              sublabel="This month"
            />
            <StatCard
              label="Saved"
              value={formatMoney(dashboard.savings_minor, dashboard.currency)}
              sublabel="This month"
            />
            <StatCard
              label="Savings rate"
              value={dashboard.savings_rate !== null ? `${dashboard.savings_rate.toFixed(0)}%` : "—"}
              sublabel="This month"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <MonthlySpendingCard spending={dashboard.monthly_spending} currency={dashboard.currency} />
            <HealthScoreMeter healthScore={dashboard.health_score} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <CategoryBreakdown items={dashboard.category_breakdown} currency={dashboard.currency} />
            <UpcomingPaymentsList payments={dashboard.upcoming_payments} currency={dashboard.currency} />
          </div>

          <RecentTransactionsList
            transactions={dashboard.recent_transactions}
            accountsById={new Map(accounts.map((a) => [a.id, a]))}
            categoriesById={new Map(categories.map((c) => [c.id, c]))}
          />
        </>
      )}
    </div>
  );
}
