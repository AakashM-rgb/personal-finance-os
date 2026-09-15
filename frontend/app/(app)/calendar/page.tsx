"use client";

import { useEffect, useState } from "react";

import { CalendarGrid } from "@/components/calendar/calendar-grid";
import { DayDetailModal } from "@/components/calendar/day-detail-modal";
import { MonthNavigator } from "@/components/calendar/month-navigator";
import { Skeleton } from "@/components/ui/skeleton";
import { listAccounts, type Account } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { getCalendarMonth, type CalendarDay, type CalendarMonth } from "@/lib/calendar";
import { listCategories, type Category } from "@/lib/categories";

export default function CalendarPage() {
  const { accessToken } = useAuth();
  const now = new Date();

  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<CalendarMonth | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState<CalendarDay | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void Promise.all([
      getCalendarMonth(accessToken, year, month),
      listAccounts(accessToken),
      listCategories(accessToken),
    ])
      .then(([calendarData, accountsData, categoriesData]) => {
        if (!isMounted) return;
        setData(calendarData);
        setAccounts(accountsData);
        setCategories(categoriesData);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setData(null);
          setError(err instanceof ApiError ? err.message : "Failed to load the calendar.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, year, month, reloadToken]);

  function handleMonthChange(nextYear: number, nextMonth: number) {
    setYear(nextYear);
    setMonth(nextMonth);
  }

  const isLoading = data === null && !error;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
            Financial Calendar
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            See spending, income, and bills laid out by day.
          </p>
        </div>
        <MonthNavigator year={year} month={month} onChange={handleMonthChange} />
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button
            type="button"
            onClick={() => setReloadToken((n) => n + 1)}
            className="font-medium underline"
          >
            Try again
          </button>
        </div>
      )}

      {isLoading && <Skeleton className="h-[32rem] w-full" />}

      {data && accounts && categories && !error && (
        <CalendarGrid data={data} onSelectDay={setSelectedDay} />
      )}

      {selectedDay && data && accounts && categories && (
        <DayDetailModal
          day={selectedDay}
          currency={data.currency}
          accounts={accounts}
          categories={categories}
          onClose={() => setSelectedDay(null)}
        />
      )}
    </div>
  );
}
